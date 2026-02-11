from flask import Flask, request, jsonify
import requests
import re
from google.oauth2 import service_account
from google.auth.transport.requests import Request

app = Flask(__name__)

# ==================================================
# CONFIGURAÇÕES
# ==================================================

API_TOKEN = "SEU_TOKEN_PIPEDRIVE"
BASE_URL = "https://api.pipedrive.com/v1"
PIPEDRIVE_DOMAIN = "https://bng.pipedrive.com"

# GOOGLE CHAT API
SERVICE_ACCOUNT_FILE = "service_account.json"
GOOGLE_CHAT_SPACE = "spaces/AAQAaEaO3xU"
SCOPES = ["https://www.googleapis.com/auth/chat.bot"]

# MAPA PIPEDRIVE USER → GOOGLE CHAT USER
USER_MAP = {
    "123456": "users/11111111111111111111",  # Allan exemplo
}

# ==================================================
# AUTENTICAÇÃO GOOGLE
# ==================================================

credentials = service_account.Credentials.from_service_account_file(
    SERVICE_ACCOUNT_FILE,
    scopes=SCOPES
)

def refresh_token():
    credentials.refresh(Request())
    return credentials.token


# ==================================================
# FUNÇÕES PIPEDRIVE API
# ==================================================

def carregar_stages():
    url = f"{BASE_URL}/stages"
    params = {"api_token": API_TOKEN}
    response = requests.get(url, params=params, timeout=10)

    stages = {}
    if response.status_code == 200:
        for stage in response.json().get("data", []):
            stages[stage["id"]] = stage["name"]

    print("✅ Stages carregados:", stages)
    return stages


def carregar_pipelines():
    url = f"{BASE_URL}/pipelines"
    params = {"api_token": API_TOKEN}
    response = requests.get(url, params=params, timeout=10)

    pipelines = {}
    if response.status_code == 200:
        for pipeline in response.json().get("data", []):
            pipelines[pipeline["id"]] = pipeline["name"]

    print("✅ Pipelines carregados:", pipelines)
    return pipelines


def gerar_link_deal(deal_id):
    return f"{PIPEDRIVE_DOMAIN}/deal/{deal_id}"


# ==================================================
# GOOGLE CHAT - ENVIO
# ==================================================

def enviar_google_chat(payload):
    token = refresh_token()

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }

    response = requests.post(
        f"https://chat.googleapis.com/v1/{GOOGLE_CHAT_SPACE}/messages",
        headers=headers,
        json=payload,
        timeout=10
    )

    print("📨 Google Chat:", response.status_code)
    if response.status_code >= 400:
        print("❌ Erro Google Chat:", response.text)


def enviar_mensagem_com_mencao(google_user_id, texto, link):
    payload = {
        "text": f"<{google_user_id}> {texto}\n{link}"
    }
    enviar_google_chat(payload)


def enviar_google_chat_card(
    titulo,
    subtitulo,
    pipeline,
    etapa,
    status,
    valor,
    link
):
    payload = {
        "cardsV2": [
            {
                "cardId": "pipedrive-deal",
                "card": {
                    "header": {
                        "title": titulo,
                        "subtitle": subtitulo
                    },
                    "sections": [
                        {
                            "widgets": [
                                {
                                    "decoratedText": {
                                        "text": f"<b>Pipeline:</b> {pipeline}"
                                    }
                                },
                                {
                                    "decoratedText": {
                                        "text": f"<b>Etapa:</b> {etapa}"
                                    }
                                },
                                {
                                    "decoratedText": {
                                        "text": f"<b>Status:</b> {status}"
                                    }
                                },
                                {
                                    "decoratedText": {
                                        "text": f"<b>Valor:</b> R$ {valor}"
                                    }
                                },
                                {
                                    "buttonList": {
                                        "buttons": [
                                            {
                                                "text": "Abrir negócio",
                                                "onClick": {
                                                    "openLink": {
                                                        "url": link
                                                    }
                                                }
                                            }
                                        ]
                                    }
                                }
                            ]
                        }
                    ]
                }
            }
        ]
    }

    enviar_google_chat(payload)


# ==================================================
# CACHE GLOBAL
# ==================================================

STAGES_MAP = carregar_stages()
PIPELINES_MAP = carregar_pipelines()


# ==================================================
# WEBHOOK PIPEDRIVE
# ==================================================

@app.route("/webhook/pipedrive", methods=["POST"])
def webhook_pipedrive():
    payload = request.json
    print("📥 Payload recebido:", payload)

    meta = payload.get("meta", {})
    data = payload.get("data", {})
    previous = payload.get("previous") or {}

    entity = meta.get("entity")
    action = meta.get("action")

    # ==================================================
    # MENÇÃO EM NOTA
    # ==================================================
    if entity == "note" and action == "create":

        content = data.get("content", "")
        mencoes = re.findall(r'@\[(\d+):([^\]]+)\]', content)

        for user_id, nome in mencoes:
            if user_id in USER_MAP:

                google_user = USER_MAP[user_id]
                deal_id = data.get("deal_id")
                deal_link = gerar_link_deal(deal_id) if deal_id else PIPEDRIVE_DOMAIN

                enviar_mensagem_com_mencao(
                    google_user,
                    f"Você foi mencionado no Pipedrive 🚨",
                    deal_link
                )

        return jsonify({"status": "ok"}), 200

    # ==================================================
    # DEALS
    # ==================================================
    if entity != "deal":
        return jsonify({"status": "ignored"}), 200

    deal_id = meta.get("entity_id")
    deal_link = gerar_link_deal(deal_id)

    pipeline_name = PIPELINES_MAP.get(
        data.get("pipeline_id"),
        f"Pipeline {data.get('pipeline_id')}"
    )

    stage_name = STAGES_MAP.get(
        data.get("stage_id"),
        f"Stage {data.get('stage_id')}"
    )

    if action == "create":
        enviar_google_chat_card(
            "🆕 Novo negócio criado",
            data.get("title"),
            pipeline_name,
            stage_name,
            data.get("status"),
            data.get("value"),
            deal_link
        )

    elif action == "change":

        if previous.get("stage_id") != data.get("stage_id"):
            prev_stage_name = STAGES_MAP.get(
                previous.get("stage_id"),
                f"Stage {previous.get('stage_id')}"
            )

            enviar_google_chat_card(
                "🔄 Negócio mudou de etapa",
                data.get("title"),
                pipeline_name,
                f"{prev_stage_name} → {stage_name}",
                data.get("status"),
                data.get("value"),
                deal_link
            )

        if previous.get("status") != data.get("status") and data.get("status") == "won":
            enviar_google_chat_card(
                "🎉 Negócio GANHO!",
                data.get("title"),
                pipeline_name,
                stage_name,
                "Ganho",
                data.get("value"),
                deal_link
            )

        if previous.get("status") != data.get("status") and data.get("status") == "lost":
            enviar_google_chat_card(
                "❌ Negócio PERDIDO",
                data.get("title"),
                pipeline_name,
                stage_name,
                "Perdido",
                data.get("value"),
                deal_link
            )

    elif action == "delete":
        enviar_google_chat_card(
            "🗑️ Negócio removido",
            data.get("title", "Não disponível"),
            pipeline_name,
            stage_name,
            "Removido",
            data.get("value", 0),
            deal_link
        )

    return jsonify({"status": "ok"}), 200


# ==================================================
# START
# ==================================================

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
