from flask import Flask, request, jsonify
import requests
import re

app = Flask(__name__)

# ==================================================
# CONFIGURAÇÕES
# ==================================================




# ==================================================
# FUNÇÕES PIPEDRIVE
# ==================================================

def carregar_stages():
    r = requests.get(f"{BASE_URL}/stages", params={"api_token": API_TOKEN})
    return {s["id"]: s["name"] for s in r.json().get("data", [])}

def listar_usuarios():
    usuarios = {}
    start = 0
    limit = 100

    while True:
        response = requests.get(
            f"{BASE_URL}/users",
            params={
                "api_token": API_TOKEN,
                "start": start,
                "limit": limit
            }
        )

        data = response.json()
        items = data.get("data", [])

        if not items:
            break

        for user in items:
            usuarios[str(user["id"])] = user["name"]

        if not data.get("additional_data", {}).get("pagination", {}).get("more_items_in_collection"):
            break

        start += limit

    return usuarios

def carregar_pipelines():
    r = requests.get(f"{BASE_URL}/pipelines", params={"api_token": API_TOKEN})
    return {p["id"]: p["name"] for p in r.json().get("data", [])}


def gerar_link_deal(deal_id):
    return f"{PIPEDRIVE_DOMAIN}/deal/{deal_id}"


# ==================================================
# GOOGLE CHAT
# ==================================================

def enviar_chat(texto):
    requests.post(GOOGLE_CHAT_WEBHOOK_URL, json={"text": texto})

def enviar_mencao(nome_usuario, edital_nome, link):

    payload = {
        "cardsV2": [{
            "cardId": "mencao",
            "card": {
                "sections": [
                    {
                        "widgets": [

                            # 🔔 Título
                            {
                                "textParagraph": {
                                    "text": "<b><font color='#00009B'>🔔 MENÇÃO EM NEGÓCIO</font></b>"
                                }
                            },

                            # 👤 Usuário
                            {
                                "decoratedText": {
                                    "startIcon": {"knownIcon": "PERSON"},
                                    "text": f"<b>{nome_usuario}</b> foi mencionado"
                                }
                            },

                            # 📄 Nome do edital
                            {
                                "textParagraph": {
                                    "text": f"<b>{edital_nome}</b>"
                                }
                            },

                            # 🔗 Botão
                            {
                                "buttonList": {
                                    "buttons": [{
                                        "text": "🔗 Abrir no Pipedrive",
                                        "onClick": {
                                            "openLink": {"url": link}
                                        }
                                    }]
                                }
                            }
                        ]
                    }
                ]
            }
        }]
    }

    requests.post(GOOGLE_CHAT_WEBHOOK_URL, json=payload)


def enviar_card(titulo, edital_nome, etapa, pipeline, valor, link, status=None, etapa_anterior=None, motivo=None):

    # =============================
    # 🎨 CORES INTELIGENTES
    # =============================
    cor_titulo = "#00009B"

    if status == "won":
        cor_titulo = "#0F9D58"
        titulo = "🏆 NEGÓCIO GANHO"

    elif status == "lost":
        cor_titulo = "#D93025"
        titulo = "❌ NEGÓCIO PERDIDO"

    # =============================
    # 💰 FORMATAÇÃO DE VALOR
    # =============================
    try:
        valor_formatado = f"R$ {float(valor):,.2f}"
    except:
        valor_formatado = f"R$ {valor}"

    destaque_valor = ""
    if float(valor or 0) >= 100000:
        destaque_valor = " 🚨 ALTO VALOR"

    emoji_pipeline = "🏛️" if "LICITA" in pipeline.upper() else "📊"

    if etapa_anterior:
        etapa = f"{etapa_anterior} ➜ {etapa}"

    # =============================
    # 📝 BLOCO MOTIVO (se perdido)
    # =============================
    motivo_widget = []

    if status == "lost" and motivo:
        motivo_widget = [{
            "textParagraph": {
                "text": f"📝 <b>Motivo:</b> {motivo}"
            }
        }]

    # =============================
    # 📦 PAYLOAD
    # =============================
    payload = {
        "cardsV2": [{
            "cardId": "deal",
            "card": {
                "sections": [{
                    "widgets": [

                        {
                            "textParagraph": {
                                "text": f"<b> {titulo}</b>"
                            }
                        },

                        {
                            "textParagraph": {
                                "text": f"<b><font color='{cor_titulo}'>{edital_nome}</font></b>"
                            }
                        },

                        {
                            "textParagraph": {
                                "text": f"📌 <b>Pipeline:</b> {emoji_pipeline} {pipeline}"
                            }
                        },

                        {
                            "textParagraph": {
                                "text": f"📍 <b>Etapa:</b> {etapa}"
                            }
                        },

                        {
                            "textParagraph": {
                                "text": f"💰 <b>Valor:</b> {valor_formatado}{destaque_valor}"
                            }
                        },

                        *motivo_widget,

                        {
                            "buttonList": {
                                "buttons": [{
                                    "text": "🔗 Abrir no Pipedrive",
                                    "onClick": {
                                        "openLink": {"url": link}
                                    }
                                }]
                            }
                        }
                    ]
                }]
            }
        }]
    }

    requests.post(GOOGLE_CHAT_WEBHOOK_URL, json=payload)

# ==================================================
# CACHE
# ==================================================

STAGES = carregar_stages()
PIPELINES = carregar_pipelines()
USERS = listar_usuarios()

print("USUÁRIOS CARREGADOS:", USERS)


# ==================================================
# WEBHOOK PIPEDRIVE
# ==================================================

CHAT_NAME_MAP = {
    "25457357": "@Alex Rocha",
    "25478587": "@Pedro Santana",
    "25402929": "@Jheniffer Barros",
    "25478587": "@Pedro Santana",
    "25370655": "@Rafael Prates",
    "25406878": "@Raquel Dias",
    "25416305": "@Silvio Possa",
    "25438459": "@Vanessa Assis",
    "25457368": "@William Cavalari",
}

@app.route("/webhook/pipedrive", methods=["POST"])
def webhook():
    payload = request.json

    meta = payload.get("meta", {})
    data = payload.get("data", {})
    previous = payload.get("previous") or {}

    entity = meta.get("entity")
    action = meta.get("action")

    # ======================
    # MENÇÕES EM NOTAS
    # ======================
    if entity == "note" and action == "create":

        content = data.get("content", "")
        print("NOTA RECEBIDA:", content)

        mencoes = re.findall(r'data-mentions="\d+:(\d+)"', content)
        print("IDS ENCONTRADOS:", mencoes)

        if mencoes:
            for user_id in mencoes:
                deal_id = data.get("deal_id")
                link = gerar_link_deal(deal_id) if deal_id else PIPEDRIVE_DOMAIN

                nome_final = CHAT_NAME_MAP.get(
                    user_id,
                    USERS.get(user_id, f"Usuário {user_id}")
                )

                enviar_mencao(
                    nome_final,
                    data.get("deal_title", "Negócio"),
                    link
                )


        return jsonify(ok=True)

    # ======================
    # IGNORAR OUTROS EVENTOS
    # ======================
    if entity != "deal":
        return jsonify(ignored=True)

    # ======================
    # DEALS
    # ======================

    deal_id = meta.get("entity_id")
    link = gerar_link_deal(deal_id)

    pipeline = PIPELINES.get(data.get("pipeline_id"), "—")
    etapa = STAGES.get(data.get("stage_id"), "—")
    valor = data.get("value", 0)

    if action == "create":
        enviar_card(
            "🆕 Novo negócio criado",
            data.get("title"),
            etapa,
            pipeline,
            valor,
            link
        )

    elif action == "change":

        # Mudança de etapa
        if previous.get("stage_id") != data.get("stage_id"):
            enviar_card(
                "🔄 Negócio mudou de etapa",
                data.get("title"),
                etapa,
                pipeline,
                valor,
                link,
                status=data.get("status"),
                etapa_anterior=STAGES.get(previous.get("stage_id"))
            )

        # Negócio ganho
        if data.get("status") == "won" and previous.get("status") != "won":
            enviar_card(
                "🎉 Negócio GANHO",
                data.get("title"),
                etapa,
                pipeline,
                valor,
                link,
                status="won"
            )

        # Negócio perdido
        if data.get("status") == "lost" and previous.get("status") != "lost":

            motivo = data.get("lost_reason") or "Não informado"

            enviar_card(
                "❌ Negócio PERDIDO",
                data.get("title"),
                etapa,
                pipeline,
                valor,
                link,
                status="lost",
                motivo=motivo
            )

    elif action == "delete":
        enviar_chat(f"🗑️ Negócio removido: {link}")

    return jsonify(ok=True)
# ==================================================
# START
# ==================================================

if __name__ == "__main__":
    app.run(port=5000, debug=True)