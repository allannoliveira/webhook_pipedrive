from flask import Flask, request, jsonify
import requests

app = Flask(__name__)

# ==================================================
# CONFIGURAÇÕES
# ==================================================

GOOGLE_CHAT_WEBHOOK_URL = "https://chat.googleapis.com/v1/spaces/AAQAaEaO3xU/messages?key=AIzaSyDdI0hCZtE6vySjMm-WEfRq3CPzqKqqsHI&token=N7jM9c673N5AaThrs3XLUaRxH3iaoYnzD7Kok9dv-dI"

API_TOKEN = "7b468a4d212b9a56888de85994e639f93505fe4c"
BASE_URL = "https://api.pipedrive.com/v1"
PIPEDRIVE_DOMAIN = "https://bng.pipedrive.com"


# ==================================================
# FUNÇÕES DE API
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
# GOOGLE CHAT — CARD AVANÇADO
# ==================================================

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
                        "subtitle": subtitulo,
                        "imageUrl": "https://cdn-icons-png.flaticon.com/512/5968/5968853.png"
                    },
                    "sections": [
                        {
                            "widgets": [
                                {
                                    "decoratedText": {
                                        "startIcon": {"knownIcon": "MAP_PIN"},
                                        "text": f"<b>Pipeline:</b> {pipeline}"
                                    }
                                },
                                {
                                    "decoratedText": {
                                        "startIcon": {"knownIcon": "BOOKMARK"},
                                        "text": f"<b>Etapa:</b> {etapa}"
                                    }
                                },
                                {
                                    "decoratedText": {
                                        "startIcon": {"knownIcon": "STAR"},
                                        "text": f"<b>Status:</b> {status}"
                                    }
                                },
                                {
                                    "decoratedText": {
                                        "startIcon": {"knownIcon": "DOLLAR"},
                                        "text": f"<b>Valor:</b> R$ {valor}"
                                    }
                                },
                                {
                                    "buttonList": {
                                        "buttons": [
                                            {
                                                "text": "🔗 Abrir negócio",
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

    response = requests.post(
        GOOGLE_CHAT_WEBHOOK_URL,
        json=payload,
        timeout=10
    )

    print("📨 Google Chat:", response.status_code)
    if response.status_code >= 400:
        print("❌ Erro Google Chat:", response.text)


# ==================================================
# CACHE GLOBAL (CARREGA NA INICIALIZAÇÃO)
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

    if meta.get("entity") != "deal":
        return jsonify({"status": "ignored"}), 200

    action = meta.get("action")
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

    # ==========================
    # 🆕 DEAL CRIADO
    # ==========================
    if action == "create":
        enviar_google_chat_card(
            titulo="🆕 Novo negócio criado",
            subtitulo=data.get("title"),
            pipeline=pipeline_name,
            etapa=stage_name,
            status=data.get("status"),
            valor=data.get("value"),
            link=deal_link
        )

    # ==========================
    # 🔄 DEAL ALTERADO
    # ==========================
    elif action == "change":

        # 🔄 Mudança de etapa
        if previous.get("stage_id") != data.get("stage_id"):
            prev_stage_name = STAGES_MAP.get(
                previous.get("stage_id"),
                f"Stage {previous.get('stage_id')}"
            )

            enviar_google_chat_card(
                titulo="🔄 Negócio mudou de etapa",
                subtitulo=data.get("title"),
                pipeline=pipeline_name,
                etapa=f"{prev_stage_name} → {stage_name}",
                status=data.get("status"),
                valor=data.get("value"),
                link=deal_link
            )

        # 🎉 GANHO
        if previous.get("status") != data.get("status") and data.get("status") == "won":
            enviar_google_chat_card(
                titulo="🎉 Negócio GANHO!",
                subtitulo=data.get("title"),
                pipeline=pipeline_name,
                etapa=stage_name,
                status="Ganho",
                valor=data.get("value"),
                link=deal_link
            )

        # ❌ PERDIDO
        if previous.get("status") != data.get("status") and data.get("status") == "lost":
            enviar_google_chat_card(
                titulo="❌ Negócio PERDIDO",
                subtitulo=data.get("title"),
                pipeline=pipeline_name,
                etapa=stage_name,
                status="Perdido",
                valor=data.get("value"),
                link=deal_link
            )

    # ==========================
    # ❌ DEAL DELETADO
    # ==========================
    elif action == "delete":
        enviar_google_chat_card(
            titulo="🗑️ Negócio removido",
            subtitulo=data.get("title", "Não disponível"),
            pipeline=pipeline_name,
            etapa=stage_name,
            status="Removido",
            valor=data.get("value", 0),
            link=deal_link
        )

    return jsonify({"status": "ok"}), 200


# ==================================================
# START
# ==================================================

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
