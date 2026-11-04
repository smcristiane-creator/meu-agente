"""
Agente de Instagram (nicho: renda extra na internet) - custo zero.
Modos:
  python agente_instagram.py gerar     -> pesquisa, escreve, cria slides e envia ao Telegram
  python agente_instagram.py publicar  -> se você respondeu OK no Telegram, publica no Instagram
"""
import os, sys, json, time, shutil, pathlib, datetime, unicodedata
import requests, feedparser
from PIL import Image, ImageDraw, ImageFont

# ---------- CONFIGURAÇÃO ----------
GEMINI_KEY = os.environ.get("GEMINI_API_KEY", "")
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.8-flash")  # confira o nome atual no Google AI Studio
TG_TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
TG_CHAT = str(os.environ.get("TELEGRAM_CHAT_ID", ""))
IG_USER_ID = os.environ.get("IG_USER_ID", "")
IG_TOKEN = os.environ.get("IG_TOKEN", "")
IG_HANDLE = os.environ.get("IG_HANDLE", "@seuperfil")
REPO = os.environ.get("GITHUB_REPOSITORY", "")
BRANCH = os.environ.get("BRANCH", "main")
GRAPH = "https://graph.facebook.com/v21.0"

FEEDS = [
    "https://news.google.com/rss/search?q=renda+extra+online&hl=pt-BR&gl=BR&ceid=BR:pt-419",
    "https://news.google.com/rss/search?q=trabalho+freelancer+MEI&hl=pt-BR&gl=BR&ceid=BR:pt-419",
    "https://news.google.com/rss/search?q=como+ganhar+dinheiro+na+internet&hl=pt-BR&gl=BR&ceid=BR:pt-419",
    "https://news.google.com/rss/search?q=golpe+renda+extra&hl=pt-BR&gl=BR&ceid=BR:pt-419",
]

PROMPT = """Você é o editor de um perfil brasileiro de Instagram sobre RENDA EXTRA NA INTERNET.
Público: pessoas comuns que querem uma renda extra com pouco ou nenhum investimento.
Tom: prático, honesto, linguagem simples, sem exagero.

REGRAS OBRIGATÓRIAS:
- NUNCA prometa ganhos garantidos, nem cite valores de ganho inventados.
- Nada de "fique rico", "método secreto", "dinheiro fácil".
- Se usar uma notícia como base, mencione a fonte de forma geral ("segundo o portal X").
- Quando fizer sentido, alerte sobre golpes e riscos.
- Não repita temas já usados.

Escolha UM tema, a partir das notícias abaixo OU de uma ideia prática atemporal (ex.: um tipo de serviço
freelancer, como começar, erros comuns, ferramentas gratuitas).

NOTÍCIAS RECENTES:
%%NOTICIAS%%

TEMAS JÁ USADOS (evite):
%%USADOS%%

Responda SOMENTE com JSON neste formato:
{
  "tema": "resumo do tema em até 80 caracteres",
  "slides": [
    {"titulo": "gancho forte da capa, até 60 caracteres", "texto": ""},
    {"titulo": "até 40 caracteres", "texto": "até 160 caracteres"},
    {"titulo": "até 40 caracteres", "texto": "até 160 caracteres"},
    {"titulo": "até 40 caracteres", "texto": "até 160 caracteres"},
    {"titulo": "até 40 caracteres", "texto": "até 160 caracteres"},
    {"titulo": "chamada final (salvar/seguir)", "texto": "até 120 caracteres"}
  ],
  "legenda": "legenda envolvente de até 900 caracteres, com uma pergunta no final",
  "hashtags": ["#rendaextra", "... até 8 hashtags relevantes"]
}"""

AVISO = "Conteúdo informativo. Os resultados variam e não há garantia de ganhos."
APROVA = {"ok", "sim", "aprovar", "aprovado", "publicar", "pode postar"}
NEGA = {"nao", "cancelar", "descartar", "rejeitar"}


# ---------- UTILITÁRIOS ----------
def ler(arq, padrao):
    p = pathlib.Path(arq)
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else padrao


def salvar(arq, dados):
    pathlib.Path(arq).write_text(json.dumps(dados, ensure_ascii=False, indent=2), encoding="utf-8")


def normalizar(t):
    t = unicodedata.normalize("NFKD", t.lower().strip())
    return "".join(c for c in t if not unicodedata.combining(c))


def tg(metodo, **kw):
    return requests.post(f"https://api.telegram.org/bot{TG_TOKEN}/{metodo}", timeout=60, **kw)


def tg_texto(txt):
    tg("sendMessage", data={"chat_id": TG_CHAT, "text": txt[:4000]})


def tg_album(arquivos):
    files, media = {}, []
    for i, p in enumerate(arquivos[:10]):
        k = f"f{i}"
        files[k] = open(p, "rb")
        media.append({"type": "photo", "media": f"attach://{k}"})
    tg("sendMediaGroup", data={"chat_id": TG_CHAT, "media": json.dumps(media)}, files=files)


# ---------- 1. PESQUISA ----------
def pesquisar():
    itens = []
    for url in FEEDS:
        try:
            for e in feedparser.parse(url).entries[:6]:
                itens.append({"titulo": e.get("title", ""), "link": e.get("link", "")})
        except Exception as ex:
            print("Falha no feed:", url, ex)
    return itens[:24]


# ---------- 2. PRODUÇÃO ----------
def gerar_conteudo(noticias, historico):
    lista = "\n".join(f"- {n['titulo']}" for n in noticias) or "(sem notícias hoje)"
    usados = "\n".join(f"- {t}" for t in historico[-30:]) or "(nenhum)"
    prompt = PROMPT.replace("%%NOTICIAS%%", lista).replace("%%USADOS%%", usados)
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent?key={GEMINI_KEY}"
    corpo = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"responseMimeType": "application/json", "temperature": 0.8},
    }
    ultimo_erro = None
    for tentativa in range(3):
        r = requests.post(url, json=corpo, timeout=90)
        if r.ok:
            texto = r.json()["candidates"][0]["content"]["parts"][0]["text"]
            texto = texto.strip().removeprefix("```json").removesuffix("```").strip()
            c = json.loads(texto)
            if len(c["slides"]) >= 4:
                return c
            ultimo_erro = "slides insuficientes"
        else:
            ultimo_erro = r.text
        time.sleep(10)
    raise RuntimeError(f"Falha ao gerar conteúdo: {ultimo_erro}")


W, H = 1080, 1350
BG, AC, TX, MUTED = (15, 23, 42), (34, 197, 94), (241, 245, 249), (148, 163, 184)


def fonte(tam):
    for c in ("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", "DejaVuSans-Bold.ttf"):
        try:
            return ImageFont.truetype(c, tam)
        except OSError:
            pass
    return ImageFont.load_default()


def quebrar(draw, texto, fnt, larg):
    linhas, atual = [], ""
    for pal in texto.split():
        teste = (atual + " " + pal).strip()
        if draw.textlength(teste, font=fnt) <= larg:
            atual = teste
        else:
            linhas.append(atual)
            atual = pal
    if atual:
        linhas.append(atual)
    return linhas


def desenhar_slides(c, pasta):
    pathlib.Path(pasta).mkdir(parents=True, exist_ok=True)
    total = len(c["slides"])
    arquivos = []
    for i, s in enumerate(c["slides"]):
        img = Image.new("RGB", (W, H), BG)
        d = ImageDraw.Draw(img)
        margem, larg = 90, W - 180
        capa = i == 0
        f_tit = fonte(88 if capa else 66)
        f_txt = fonte(44)
        l_tit = quebrar(d, s.get("titulo", ""), f_tit, larg)
        l_txt = quebrar(d, s.get("texto", ""), f_txt, larg) if s.get("texto") else []
        alt_tit = len(l_tit) * int(f_tit.size * 1.25)
        alt_txt = len(l_txt) * int(f_txt.size * 1.45)
        bloco = alt_tit + (50 if l_txt else 0) + alt_txt
        y = (H - bloco) // 2 if capa or i == total - 1 else 260
        d.rectangle([margem, y - 40, margem + 120, y - 28], fill=AC)
        for ln in l_tit:
            d.text((margem, y), ln, font=f_tit, fill=AC if not capa else TX)
            y += int(f_tit.size * 1.25)
        y += 50
        for ln in l_txt:
            d.text((margem, y), ln, font=f_txt, fill=TX)
            y += int(f_txt.size * 1.45)
        d.text((margem, H - 110), IG_HANDLE, font=fonte(36), fill=MUTED)
        d.text((W - margem - 90, H - 110), f"{i + 1}/{total}", font=fonte(36), fill=MUTED)
        if i == total - 1:
            d.text((margem, H - 190), AVISO[:60] + "...", font=fonte(26), fill=MUTED)
        caminho = f"{pasta}/slide_{i + 1}.jpg"
        img.save(caminho, "JPEG", quality=92)
        arquivos.append(caminho)
    return arquivos


def montar_legenda(c):
    tags = " ".join(c.get("hashtags", [])[:8])
    return f"{c['legenda']}\n\n{AVISO}\n\n{tags}".strip()[:2150]


def modo_gerar():
    pend = ler("pendente.json", {})
    if pend.get("status") == "aguardando":
        pend["status"] = "expirado"
        salvar("pendente.json", pend)
    hist = ler("historico.json", [])
    c = gerar_conteudo(pesquisar(), hist)
    pasta = f"posts/{datetime.datetime.utcnow():%Y%m%d-%H%M}"
    arquivos = desenhar_slides(c, pasta)
    legenda = montar_legenda(c)
    salvar("pendente.json", {
        "status": "aguardando", "pasta": pasta, "n": len(arquivos),
        "legenda": legenda, "tema": c["tema"], "criado_ts": int(time.time()),
    })
    # limpa pastas antigas (mantém as 10 mais recentes)
    pastas = sorted(p for p in pathlib.Path("posts").iterdir() if p.is_dir())
    for p in pastas[:-10]:
        shutil.rmtree(p, ignore_errors=True)
    tg_album(arquivos)
    tg_texto(f"TEMA: {c['tema']}\n\nLEGENDA:\n{legenda}\n\nResponda OK para publicar ou NAO para descartar.")


# ---------- 3. APROVAÇÃO + POSTAGEM ----------
def ultima_resposta(desde_ts):
    r = tg("getUpdates", data={"timeout": 0}).json()
    resp = None
    for u in r.get("result", []):
        m = u.get("message") or {}
        if str((m.get("chat") or {}).get("id")) != TG_CHAT or m.get("date", 0) < desde_ts:
            continue
        t = normalizar(m.get("text", ""))
        if t in APROVA or t in NEGA:
            resp = t
    return resp


def ig_post(caminho, **dados):
    r = requests.post(f"{GRAPH}/{caminho}", data={**dados, "access_token": IG_TOKEN}, timeout=90)
    if not r.ok:
        raise RuntimeError(f"Erro Instagram: {r.text}")
    return r.json()


def esperar_container(cid):
    for _ in range(20):
        r = requests.get(f"{GRAPH}/{cid}", params={"fields": "status_code", "access_token": IG_TOKEN}, timeout=60).json()
        if r.get("status_code") == "FINISHED":
            return
        if r.get("status_code") == "ERROR":
            raise RuntimeError(f"Container com erro: {r}")
        time.sleep(5)
    raise RuntimeError("Tempo esgotado esperando o Instagram processar.")


def publicar(pend):
    base = f"https://raw.githubusercontent.com/{REPO}/{BRANCH}/{pend['pasta']}"
    filhos = []
    for i in range(pend["n"]):
        r = ig_post(f"{IG_USER_ID}/media", image_url=f"{base}/slide_{i + 1}.jpg", is_carousel_item="true")
        filhos.append(r["id"])
    for f in filhos:
        esperar_container(f)
    car = ig_post(f"{IG_USER_ID}/media", media_type="CAROUSEL", children=",".join(filhos), caption=pend["legenda"])
    esperar_container(car["id"])
    return ig_post(f"{IG_USER_ID}/media_publish", creation_id=car["id"])


def modo_publicar():
    pend = ler("pendente.json", {})
    if pend.get("status") != "aguardando":
        print("Nada pendente.")
        return
    if time.time() - pend["criado_ts"] > 20 * 3600:
        pend["status"] = "expirado"
        salvar("pendente.json", pend)
        tg_texto("O post de hoje expirou sem aprovação.")
        return
    resp = ultima_resposta(pend["criado_ts"])
    if resp is None:
        print("Sem resposta ainda.")
        return
    if resp in NEGA:
        pend["status"] = "descartado"
        salvar("pendente.json", pend)
        tg_texto("Post descartado.")
        return
    try:
        publicar(pend)
    except Exception as e:
        tg_texto(f"Falha ao publicar: {e}"[:1000])
        raise
    pend["status"] = "publicado"
    salvar("pendente.json", pend)
    hist = ler("historico.json", [])
    hist.append(pend["tema"])
    salvar("historico.json", hist[-60:])
    tg_texto("Publicado no Instagram!")


if __name__ == "__main__":
    modo = sys.argv[1] if len(sys.argv) > 1 else "gerar"
    {"gerar": modo_gerar, "publicar": modo_publicar}[modo]()
