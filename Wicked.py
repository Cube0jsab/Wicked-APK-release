from flask import Flask, request, jsonify
import urllib.request
import urllib.parse
import urllib.error
import re
import json
import os

app = Flask(__name__)

# ВСТАВЬТЕ СВОЙ КЛЮЧ СЮДА (или задайте переменную окружения GROQ_API_KEY)
API_KEY = os.environ.get("GROQ_API_KEY", "")
API_URL = "https://api.groq.com/openai/v1/chat/completions"
MODEL = "openai/gpt-oss-120b"
SMALL_MODEL = "llama-3.1-8b-instant"  # лёгкая модель для памяти и названий: экономит лимит основной

base_prompt = "Твое имя — Викед. Ты — обычный ИИ-помощник: вежливый, спокойный, отвечаешь по делу, без игривости и без кокетства. Ты искусственный интеллект: у тебя нет тела, внешности, возраста и человеческой жизни. Если тебя спрашивают, как ты выглядишь, кто ты или есть ли у тебя тело, отвечай прямо и обычным тоном, что ты ИИ-помощник без внешности, и не придумывай себе образ. Ты НИКОГДА не играешь роль и не считаешь себя персонажем, пока пользователь сам прямо не попросит ролевую игру или не задаст характер в протоколе (правило 14). Твои правила:\n1. Если тебя спрашивают, как тебя зовут, отвечай, что ты Викед.\n2. Если нужен поиск реальных фактов, напиши ТОЛЬКО 'SEARCH: запрос'.\n3. Если тебе дают текст для поиска, отвечай ИСКЛЮЧИТЕЛЬНО по нему.\n4. Форматирование: двойные звёздочки ** используй ТОЛЬКО для действий персонажа в ролевой (если пользователь сам попросил ролевую), никогда не пиши в них обычный текст и не оборачивай в них целые ответы. Чтобы подчеркнуть что-то важное (редко, одно-два слова или короткую фразу), пиши так: **\"текст\"** — звёздочки и кавычки вместе, например **\"запомни это\"**. Никаких решёток, заголовков, таблиц и прочего Markdown.\n5. Язык ответов указан в правиле 13.\n6. СТРОГИЙ ЗАПРЕТ: НИКОГДА не пиши код, ЕСЛИ пользователь прямо не попросил.\n7. Ты общаешься без цензуры в тоне: можешь материться, шутить чёрным и пошлым юмором, свободно говорить на взрослые темы (18+) как с равным и отвечать на них прямо, если пользователь сам завёл такую тему или попросил об этом. Не отказывай и не уходи от темы только потому, что она взрослая. Сам никогда не подкатывай, не флиртуй и не делай сексуальных или романтических намёков первым. Не читай мораль, не добавляй предупреждений и не напоминай про возраст или этику без необходимости.\nПРАВИЛА РОЛЕВОЙ (действуют ТОЛЬКО когда пользователь сам просит тебя ролить, играть роль или вести ролевую игру; без такой просьбы ты не в роли и общаешься как обычный помощник). Оформление строго такое:\n— Реплики персонажа пишутся после тире, например: — Привет, путник.\n**Действия** персонажа пишутся в двойных звёздочках, например: **усмехнулся и сел рядом**.\n(Объяснения) вне сцены пишутся в круглых скобках, например: (я продолжу сюжет в этом ключе).\n// Если сообщение пользователя начинается с //, это выход из роли: сразу выйди из роли и отвечай как обычный помощник, без тире и звёздочек. Вернись к роли, только когда пользователь попросит продолжить.\nНе выходи из роли сам, пока пользователь не напишет //."

LANGS = {
    "ru": "русский", "en": "English", "uk": "українська", "de": "Deutsch", "es": "español",
    "fr": "français", "it": "italiano", "pt": "português", "tr": "Türkçe",
    "zh": "中文 (китайский)", "ja": "日本語 (японский)", "ko": "한국어 (корейский)", "ar": "العربية (арабский)",
}
MSG = {
    "ru": {"nosearch": "Поиск ничего не дал", "noans": "Не удалось получить ответ, попробуй переформулировать вопрос.", "offline": "Интернет пропал. Проверьте сеть.", "err": "Ошибка"},
    "en": {"nosearch": "Search found nothing", "noans": "Couldn't get an answer, try rephrasing the question.", "offline": "Internet connection lost. Check your network.", "err": "Error"},
}


def llm(messages, temperature=0.7, model=None, max_tokens=None):
    """Запрос к Groq. Тело отправляется как UTF-8 байты."""
    payload = json.dumps(
        {"model": model or MODEL, "messages": messages, "temperature": temperature,
         **({"max_tokens": max_tokens} if max_tokens else {})},
        ensure_ascii=False,
    ).encode("utf-8")
    req = urllib.request.Request(
        API_URL,
        data=payload,
        headers={
            "Content-Type": "application/json; charset=utf-8",
            "Authorization": "Bearer " + API_KEY.strip(),
            "User-Agent": "Mozilla/5.0",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="ignore")
        raise RuntimeError(f"HTTP {e.code}: {body[:300]}")
    return data["choices"][0]["message"]["content"] or ""


def llm_small(messages, temperature=0.3, max_tokens=300):
    """Лёгкая модель; если она недоступна, откатываемся на основную."""
    try:
        return llm(messages, temperature=temperature, model=SMALL_MODEL, max_tokens=max_tokens)
    except Exception:
        return llm(messages, temperature=temperature, max_tokens=max_tokens)


def get_wikipedia_text(query):
    try:
        url = f"https://ru.wikipedia.org/w/api.php?action=query&list=search&utf8=&format=json&srsearch={urllib.parse.quote(query)}"
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        data = json.loads(urllib.request.urlopen(req, timeout=8).read().decode('utf-8'))
        for result in data['query']['search'][:3]:
            page_title = result['title']
            page_url = f"https://ru.wikipedia.org/w/api.php?action=query&prop=extracts&explaintext=1&format=json&titles={urllib.parse.quote(page_title)}"
            page_data = json.loads(urllib.request.urlopen(urllib.request.Request(page_url, headers={'User-Agent': 'Mozilla/5.0'}), timeout=8).read().decode('utf-8'))
            for page_id in page_data['query']['pages']:
                text = page_data['query']['pages'][page_id].get('extract', '')
                if text and len(text) > 200:
                    return text[:3000]
    except Exception:
        pass
    return None


def web_search(query):
    try:
        url = "https://html.duckduckgo.com/html/?q=" + urllib.parse.quote(query)
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        html = urllib.request.urlopen(req, timeout=8).read().decode('utf-8', errors='ignore')
        results = re.findall(r'class="result__a".*?>(.*?)</a>.*?result__snippet".*?>(.*?)</a>', html, re.DOTALL)
        text_res = ""
        for title, snippet in results[:4]:
            text_res += f"- {re.sub('<.*?>', '', title)}: {re.sub('<.*?>', '', snippet)}\n"
        if text_res:
            return text_res
    except Exception:
        pass
    try:
        url = "https://lite.duckduckgo.com/lite/?q=" + urllib.parse.quote(query)
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        html = urllib.request.urlopen(req, timeout=8).read().decode('utf-8', errors='ignore')
        snippets = re.findall(r"class='result-snippet'>(.*?)</td>", html, re.DOTALL)
        text_res = "".join("- " + re.sub('<.*?>', '', x).strip() + "\n" for x in snippets[:4])
        return text_res or None
    except Exception:
        return None


HTML_PAGE = r"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <title>Викед</title>
    <style>
        :root {
            --bg: #0e1621; --panel: #17212b; --msg-user: #2b5278; --msg-bot: #182533;
            --text: #ffffff; --accent: #5288c1; --muted: #7d8b99; --border: #101921;
            --hover: #202b36; --overlay: rgba(0,0,0,0.6); --danger: #e74c3c; --bold: #b5bcc6;
        }
        * { box-sizing: border-box; }
        body { font-family: 'Segoe UI', Tahoma, sans-serif; background-color: var(--bg); color: var(--text); margin: 0; padding: 0; display: flex; flex-direction: column; height: 100vh; height: 100dvh; overflow: hidden; transition: background-color 0.25s, color 0.25s; }

        header { display: flex; align-items: center; background-color: var(--panel); padding: 12px 15px; border-bottom: 1px solid var(--border); z-index: 10; flex-shrink: 0; }
        #burger-btn { font-size: 24px; cursor: pointer; margin-right: 15px; user-select: none; -webkit-user-select: none; }
        #current-chat-title { font-weight: bold; font-size: 16px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; min-width: 0; cursor: pointer; user-select: none; -webkit-user-select: none; }
        #new-chat-top { margin-left: auto; padding-left: 12px; cursor: pointer; display: flex; align-items: center; user-select: none; -webkit-user-select: none; }
        #new-chat-top svg { width: 28px; height: 28px; transition: transform 0.15s; stroke: var(--text); }
        #new-chat-top:active svg { transform: scale(0.88); }

        #toast { position: fixed; top: 64px; right: 12px; background: var(--hover); color: var(--text); padding: 10px 16px; border-radius: 10px; font-size: 14px; z-index: 100; box-shadow: 0 4px 15px rgba(0,0,0,0.4); opacity: 0; pointer-events: none; transform: translateY(-8px); transition: 0.25s; max-width: 80%; }
        #toast.show { opacity: 1; transform: translateY(0); }

        #sidebar { position: fixed; top: 0; left: -300px; width: 300px; height: 100%; background-color: var(--panel); z-index: 20; transition: 0.3s; display: flex; flex-direction: column; box-shadow: 2px 0 10px rgba(0,0,0,0.4); }
        #sidebar.open { left: 0; }
        #sidebar-header { padding: 15px; border-bottom: 1px solid var(--border); display: flex; justify-content: space-between; align-items: center; }
        #chat-list { flex: 1; overflow-y: auto; padding: 10px; }
        #sidebar-footer { padding: 12px 15px; border-top: 1px solid var(--border); display: flex; justify-content: flex-end; flex-shrink: 0; }
        #settings-btn { cursor: pointer; display: flex; padding: 4px; user-select: none; -webkit-user-select: none; }
        #settings-btn svg { width: 26px; height: 26px; stroke: #8a8f98; fill: none; stroke-width: 1.8; stroke-linecap: round; stroke-linejoin: round; transition: transform 0.3s; }
        #settings-btn:active svg { transform: rotate(60deg); }

        .chat-item { padding: 12px; border-radius: 8px; cursor: pointer; margin-bottom: 5px; background-color: var(--bg); display: flex; flex-direction: column; user-select: none; -webkit-user-select: none; position: relative; }
        .chat-item:hover { background-color: var(--hover); }
        .chat-item-title { font-size: 14px; font-weight: bold; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; padding-right: 20px; }
        .chat-item-date { font-size: 11px; color: var(--muted); margin-top: 4px; }
        .chat-item.active { border-left: 3px solid var(--accent); background-color: var(--hover); }
        .pin-icon { position: absolute; right: 10px; top: 50%; transform: translateY(-50%); font-size: 16px; color: var(--muted); }

        #overlay { position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: var(--overlay); z-index: 15; display: none; }
        #overlay.open { display: block; }

        .modal { position: fixed; top: 50%; left: 50%; transform: translate(-50%, -50%); background: var(--panel); color: var(--text); padding: 20px; border-radius: 12px; z-index: 30; display: none; width: 80%; max-width: 300px; box-shadow: 0 4px 15px rgba(0,0,0,0.4); flex-direction: column; gap: 10px; }
        .modal.open { display: flex; }
        .modal button { background: var(--bg); color: var(--text); border: none; padding: 12px; border-radius: 8px; font-size: 15px; cursor: pointer; text-align: left; transition: 0.2s; }
        .modal button:hover { background: var(--hover); }
        .modal button.danger { color: var(--danger); }
        .modal-title { font-weight: bold; margin-bottom: 5px; color: var(--muted); word-wrap: break-word; }
        .modal .cancel { text-align: center; margin-top: 5px; color: var(--muted); }

        /* ---------- Страница настроек ---------- */
        #settings-page { position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: var(--bg); color: var(--text); z-index: 50; display: none; flex-direction: column; }
        #settings-page.open { display: flex; }
        .sp-header { display: flex; align-items: center; gap: 14px; padding: 12px 16px; background: var(--panel); border-bottom: 1px solid var(--border); flex-shrink: 0; }
        .sp-x { font-size: 22px; cursor: pointer; user-select: none; -webkit-user-select: none; width: 38px; height: 38px; display: flex; align-items: center; justify-content: center; }
        .sp-title { font-size: 18px; font-weight: bold; flex: 1; }
        .sp-ok { width: 38px; height: 38px; border-radius: 50%; background: var(--accent); color: #ffffff; display: flex; align-items: center; justify-content: center; font-size: 22px; font-weight: bold; cursor: pointer; user-select: none; -webkit-user-select: none; }
        .sp-ok:active { transform: scale(0.9); }
        .sp-layout { flex: 1; display: flex; min-height: 0; }
        .sp-tabs { width: 142px; flex-shrink: 0; background: var(--panel); border-right: 1px solid var(--border); display: flex; flex-direction: column; gap: 8px; padding: 12px 8px; }
        .sp-tab { display: flex; align-items: center; gap: 8px; padding: 12px 8px; border-radius: 10px; font-size: 13px; font-weight: 600; white-space: nowrap; cursor: pointer; color: var(--text); user-select: none; -webkit-user-select: none; border: 2px solid transparent; }
        .sp-tab svg { width: 20px; height: 20px; flex-shrink: 0; stroke: currentColor; fill: none; stroke-width: 1.9; stroke-linecap: round; stroke-linejoin: round; }
        .sp-tab .star { width: 20px; text-align: center; font-size: 18px; flex-shrink: 0; }
        .sp-tab.active { background: var(--accent); color: #ffffff; }
        .sp-empty { flex: 1; display: flex; align-items: center; justify-content: center; text-align: center; color: var(--muted); font-size: 14px; padding: 20px; }
        .sp-body.nothing .sp-inner { display: none; }
        .sp-body:not(.nothing) .sp-empty { display: none; }
        #delete-page, #loader-page { position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: var(--bg); color: var(--text); display: none; flex-direction: column; align-items: center; justify-content: center; padding: 24px; text-align: center; gap: 16px; }
        #delete-page { z-index: 60; }
        #loader-page { z-index: 90; }
        #delete-page.open, #loader-page.open { display: flex; }
        .confirm-title { font-size: 26px; font-weight: bold; }
        .confirm-text { max-width: 340px; font-size: 14px; color: var(--muted); line-height: 1.5; }
        .confirm-box { width: 100%; max-width: 340px; display: flex; flex-direction: column; gap: 10px; }
        .danger-btn { background: #e74c3c; color: #ffffff; border: none; border-radius: 10px; padding: 13px; font-size: 15px; font-weight: bold; cursor: pointer; width: 100%; }
        .danger-btn:disabled { opacity: 0.4; cursor: default; }
        .big-spinner { width: 46px; height: 46px; border: 4px solid var(--muted); border-top-color: var(--text); border-radius: 50%; animation: spin 0.9s linear infinite; }
        input[type=range] { width: 100%; accent-color: var(--accent); }
        .fs-row { display: flex; align-items: center; gap: 10px; }
        .fs-row .fs-val { min-width: 48px; text-align: right; font-weight: bold; }
        .sp-pane { display: none; }
        .sp-pane.active { display: flex; flex-direction: column; gap: 14px; }
        .ai-note { background: var(--bg); border-radius: 10px; padding: 12px; font-size: 14px; line-height: 1.45; color: var(--muted); }
        #ai-notice { text-align: center; font-size: 12px; color: var(--muted); padding: 5px 12px 0; background: var(--panel); flex-shrink: 0; }
        .sp-body { flex: 1; overflow-y: auto; padding: 16px; background: var(--hover); display: flex; flex-direction: column; min-width: 0; }
        .sp-inner { width: 100%; max-width: 620px; margin: 0 auto; display: flex; flex-direction: column; gap: 14px; }
        .sp-card { background: var(--panel); border-radius: 14px; padding: 16px; display: flex; flex-direction: column; gap: 10px; }
        .section-title { font-weight: bold; font-size: 16px; color: var(--accent); }
        .sub-label { font-size: 13px; color: var(--muted); margin-top: 4px; }
        .opt-row { display: flex; gap: 10px; }
        .opt-btn { flex: 1; background: var(--bg); color: var(--text); border: 2px solid transparent; padding: 13px 10px; border-radius: 10px; font-size: 15px; cursor: pointer; text-align: center; }
        .opt-btn.active { border-color: var(--accent); }
        .opt-desc { font-size: 13px; color: var(--muted); line-height: 1.4; }
        .text-field { width: 100%; padding: 12px 14px; border-radius: 10px; border: 2px solid transparent; background: var(--bg); color: var(--text); font-size: 16px; outline: none; }
        .text-field:focus { border-color: var(--accent); }
        .swatches { display: flex; flex-wrap: wrap; gap: 10px; align-items: center; }
        .swatch { width: 38px; height: 38px; border-radius: 50%; cursor: pointer; border: 2px solid var(--muted); }
        .swatch.active { border-color: var(--accent); box-shadow: 0 0 0 2px var(--accent); }
        .swatches input[type=color] { width: 42px; height: 42px; border: none; background: none; padding: 0; cursor: pointer; }
        .preview { background: var(--bg); border-radius: 12px; padding: 12px; display: flex; flex-direction: column; }

        /* ---------- Первый вход ---------- */
        #welcome-screen { position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: var(--bg); color: var(--text); z-index: 80; display: none; align-items: center; justify-content: center; padding: 20px; }
        #welcome-screen.open { display: flex; }
        .welcome-card { width: 100%; max-width: 360px; background: var(--panel); border-radius: 16px; padding: 24px; display: flex; flex-direction: column; gap: 12px; text-align: center; }
        .welcome-title { font-size: 22px; font-weight: bold; }

        /* ---------- Сообщения ---------- */
        #chat-wrap { position: relative; flex: 1; min-height: 0; display: flex; flex-direction: column; }
        #chat-area { flex: 1; min-height: 0; overflow-y: auto; padding: 15px; display: flex; flex-direction: column; }
        #scroll-down-btn { position: absolute; right: 14px; bottom: 12px; width: 42px; height: 42px; border-radius: 50%; background: var(--panel); border: 1px solid var(--border); box-shadow: 0 2px 10px rgba(0,0,0,0.35); display: flex; align-items: center; justify-content: center; cursor: pointer; opacity: 0; pointer-events: none; transform: translateY(10px); transition: opacity 0.25s, transform 0.25s; user-select: none; -webkit-user-select: none; z-index: 5; }
        #scroll-down-btn.show { opacity: 1; pointer-events: auto; transform: translateY(0); }
        #scroll-down-btn:active { transform: scale(0.9); }
        #scroll-down-btn svg { width: 22px; height: 22px; stroke: var(--text); fill: none; stroke-width: 2; stroke-linecap: round; stroke-linejoin: round; }

        .welcome-center { margin: auto; max-width: 80%; text-align: center; color: var(--text); font-size: var(--fs, 15px); line-height: 1.45; padding: 14px 20px; border-radius: 16px; border: 1.5px solid var(--muted); border: 1.5px solid color-mix(in srgb, var(--text) 40%, var(--bg)); background: transparent; user-select: none; -webkit-user-select: none; }
        .message-wrapper { max-width: 85%; margin-bottom: 8px; display: flex; flex-direction: column; }
        .message-wrapper.user { align-self: flex-end; align-items: flex-end; }
        .message-wrapper.bot { align-self: flex-start; align-items: flex-start; }
        .message { padding: 10px 14px; border-radius: 12px; font-size: var(--fs, 15px); line-height: 1.4; word-wrap: break-word; white-space: pre-wrap; user-select: none; -webkit-user-select: none; -webkit-touch-callout: none; }
        .user .message { background-color: var(--msg-user); border-bottom-right-radius: 2px; }
        .bot .message { background-color: var(--msg-bot); border-bottom-left-radius: 2px; }
        .bold-text { font-weight: 800; color: var(--bold); }
        .big-text { font-size: 1.3em; font-weight: 700; }

        .anim-in { animation: popIn 0.28s ease-out; }
        @keyframes popIn { from { opacity: 0; transform: translateY(10px) scale(0.97); } to { opacity: 1; transform: translateY(0) scale(1); } }

        .status { font-size: 12px; color: var(--muted); font-style: italic; margin-bottom: 4px; display: flex; align-items: center; gap: 5px; }
        .spinner { border: 2px solid var(--muted); border-top: 2px solid transparent; border-radius: 50%; width: 10px; height: 10px; animation: spin 1s linear infinite; }
        @keyframes spin { 0% { transform: rotate(0deg); } 100% { transform: rotate(360deg); } }

        .loading-dots::after { content: ''; animation: dots 1.5s steps(4, end) infinite; }
        @keyframes dots { 0%, 20% { content: ''; } 40% { content: '•'; } 60% { content: '••'; } 80%, 100% { content: '•••'; } }

        .msg-controls { display: flex; align-items: center; gap: 10px; margin-top: 4px; font-size: 13px; color: var(--muted); }
        .msg-controls span { cursor: pointer; user-select: none; -webkit-user-select: none; transition: 0.2s; }
        .msg-controls span:hover { color: var(--accent); }
        .msg-controls span.disabled { opacity: 0.3; cursor: not-allowed; }

        #input-area { display: flex; padding: 6px 10px 10px; background-color: var(--panel); align-items: center; flex-shrink: 0; border-top: 1px solid var(--border); }
        #text-input { flex: 1; padding: 12px 15px; border: none; border-radius: 20px; outline: none; font-size: 16px; background-color: var(--bg); color: var(--text); margin-right: 10px; }
        .send-btn { border: none; border-radius: 50%; width: 45px; height: 45px; cursor: pointer; display: flex; align-items: center; justify-content: center; background-color: var(--accent); color: white; font-size: 18px; transition: 0.2s; }
        .send-btn:active { transform: scale(0.9); }
        .send-btn .ic-stop { display: none; width: 18px; height: 18px; margin: 0; fill: white; }
        .send-btn.stopping .ic-send { display: none; }
        .send-btn.stopping .ic-stop { display: block; }
        html { height: 100%; position: relative; overflow-x: hidden; overflow-y: auto; overscroll-behavior: none; }
        #ptr-pad { position: absolute; top: 0; left: 0; width: 1px; height: calc(100% + 2px); pointer-events: none; visibility: hidden; }
        #sidebar-footer { align-items: center; justify-content: space-between !important; gap: 10px; }
        #profile-badge { display: flex; align-items: center; gap: 10px; min-width: 0; flex: 1; }
        #profile-name { font-weight: bold; font-size: 15px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
        .avatar { border-radius: 50%; background: var(--accent); color: #ffffff; display: flex; align-items: center; justify-content: center; font-weight: bold; overflow: hidden; flex-shrink: 0; background-size: cover; background-position: center; }
        .avatar-sm { width: 38px; height: 38px; font-size: 17px; }
        .avatar-big { width: 72px; height: 72px; font-size: 30px; }
        .avatar-row { display: flex; align-items: center; gap: 14px; }
        .avatar-btns { flex: 1; display: flex; flex-direction: column; gap: 8px; }
        .avatar-btns .opt-btn { flex: none; padding: 10px; font-size: 14px; }
        .check-row { display: flex; align-items: flex-start; gap: 10px; font-size: 13px; color: var(--muted); line-height: 1.4; cursor: pointer; }
        .check-row input { width: 20px; height: 20px; margin: 0; flex-shrink: 0; accent-color: var(--accent); }

        body { overscroll-behavior: none; }
        #chat-area, .sp-body, #chat-list { overscroll-behavior: contain; }
        #bg-layer { position: fixed; top: -30px; left: -30px; right: -30px; bottom: -30px; background-size: cover; background-position: center; z-index: -1; display: none; pointer-events: none; }
        .msg-time { font-size: 11px; color: var(--muted); margin-top: 3px; }
        .msg-stopped { font-style: italic; color: var(--muted); }
        .msg-controls span.cont-btn { color: var(--accent); font-weight: bold; }
        textarea.text-field { resize: vertical; font-family: inherit; line-height: 1.4; min-height: 110px; }
        select.text-field { appearance: auto; }
        .btn-red { color: #e74c3c; }
        #bg-editor { position: fixed; top: 0; left: 0; width: 100%; height: 100%; z-index: 75; display: none; flex-direction: column; color: #ffffff; background: #000000; overflow: hidden; }
        #bg-editor.open { display: flex; }
        #bg-ed-img { position: absolute; top: -30px; left: -30px; right: -30px; bottom: -30px; background-size: cover; background-position: center; }
        .bg-ed-top { position: relative; z-index: 1; display: flex; align-items: center; gap: 14px; padding: 12px 16px; background: rgba(0,0,0,0.4); }
        .bg-ed-title { flex: 1; font-size: 18px; font-weight: bold; }
        .bg-ed-sample { position: relative; z-index: 1; flex: 1; padding: 16px; display: flex; flex-direction: column; justify-content: flex-end; min-height: 0; }
        .bg-ed-panel { position: relative; z-index: 1; margin: 12px; padding: 14px; border-radius: 14px; background: rgba(0,0,0,0.6); display: flex; flex-direction: column; gap: 12px; }
        .bg-ed-row { display: flex; align-items: center; gap: 10px; }
        .bg-ed-row > span:first-child { min-width: 84px; font-size: 14px; }
        .bg-ed-row .fs-val { min-width: 52px; }
        .send-btn svg { width: 22px; height: 22px; fill: white; margin-left: -2px; margin-top: 2px; }
    </style>
</head>
<body>
    <div id="bg-layer"></div>

    <div id="sidebar">
        <div id="sidebar-header">
            <span style="font-weight: bold; font-size: 18px;" data-i18n="chats">Мои чаты</span>
            <span style="cursor:pointer; font-size: 20px;" onclick="closeAllModals()">✖</span>
        </div>
        <div id="chat-list"></div>
        <div id="sidebar-footer">
            <div id="profile-badge"><div class="avatar avatar-sm" id="avatar-sm"></div><span id="profile-name"></span></div>
            <div id="settings-btn" onclick="openSettings()" title="Настройки" data-i18n-title="settings">
                <svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
                    <circle cx="12" cy="12" r="3"/>
                    <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z"/>
                </svg>
            </div>
        </div>
    </div>

    <div id="overlay" onclick="closeAllModals()"></div>

    <!-- Действия с чатом -->
    <div id="action-modal" class="modal">
        <div class="modal-title" id="modal-chat-title">Действия</div>
        <button onclick="renameChat()" data-i18n="rename">✎ Переименовать</button>
        <button onclick="pinChat()" data-i18n="pin">✪ Закрепить/Открепить</button>
        <button class="danger" onclick="deleteChat()" data-i18n="delete">🗑️ Удалить</button>
        <button class="cancel" onclick="closeActionModal()" data-i18n="cancel">Отмена</button>
    </div>

    <!-- Действия с сообщением -->
    <div id="msg-modal" class="modal">
        <div class="modal-title" id="msg-modal-title">Сообщение</div>
        <button id="msg-edit-btn" onclick="editMessage()" data-i18n="edit">✎ Изменить</button>
        <button onclick="copyMessageFromModal()" data-i18n="copy">❐ Копировать</button>
        <button class="danger" onclick="deleteMessage()" data-i18n="delete">🗑️ Удалить</button>
        <button class="cancel" onclick="closeMsgModal()" data-i18n="cancel">Отмена</button>
    </div>

    <!-- Страница настроек -->
    <div id="settings-page">
        <div class="sp-header">
            <span class="sp-x" onclick="cancelSettings()" title="Выйти без сохранения" data-i18n-title="exit_nosave">✖</span>
            <span class="sp-title" data-i18n="settings">Настройки</span>
            <span class="sp-ok" onclick="applySettings()" title="Применить" data-i18n-title="apply">✓</span>
        </div>
        <div class="sp-layout">
            <div class="sp-tabs">
                <div class="sp-tab" data-tab="account" onclick="setTab('account')">
                    <svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg"><circle cx="12" cy="8" r="4"/><path d="M4 21c0-4.4 3.6-8 8-8s8 3.6 8 8"/></svg>
                    <span data-i18n="tab_account">Аккаунт</span>
                </div>
                <div class="sp-tab" data-tab="custom" onclick="setTab('custom')">
                    <span class="star">✦</span>
                    <span data-i18n="tab_custom">Кастомизация</span>
                </div>
                <div class="sp-tab" data-tab="lang" onclick="setTab('lang')">
                    <svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg"><circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3c2.5 2.5 3.8 5.5 3.8 9s-1.3 6.5-3.8 9c-2.5-2.5-3.8-5.5-3.8-9S9.5 5.5 12 3z"/></svg>
                    <span data-i18n="tab_lang">Язык</span>
                </div>
            </div>
            <div class="sp-body nothing" id="sp-body">
                <div class="sp-empty" data-i18n="pick_section">Выбери раздел слева</div>
                <div class="sp-inner">

                    <div class="sp-pane" id="pane-custom">
                        <div class="sp-card">
                            <div class="section-title" data-i18n="preview">Предпросмотр</div>
                            <div class="preview">
                                <div class="message-wrapper user" style="max-width:100%"><div class="message" data-i18n="prev_user">Привет, Викед!</div><div class="msg-time prev-time">12:34</div></div>
                                <div class="message-wrapper bot" style="max-width:100%"><div class="message" data-i18n-html="prev_bot">Это <b class="bold-text">действие</b> и <b class="big-text">крупный акцент</b>.</div><div class="msg-time prev-time">12:35</div></div>
                            </div>
                        </div>

                        <div class="sp-card">
                            <div class="section-title" data-i18n="scale">Масштаб интерфейса</div>
                            <div class="fs-row">
                                <span style="font-size:13px;">−</span>
                                <input type="range" id="sc-range" min="50" max="110" step="5" value="70">
                                <span style="font-size:18px;">+</span>
                                <span class="fs-val" id="sc-val">70%</span>
                            </div>
                            <div class="opt-desc" data-i18n="scale_desc">Одинаково на телефоне и на компьютере. Если всё кажется слишком крупным, уменьши.</div>
                            <button class="opt-btn" style="flex:none;" onclick="setScale(70)" data-i18n="scale_std">Стандартный (70%)</button>
                        </div>

                        <div class="sp-card">
                            <div class="section-title" data-i18n="font">Размер шрифта</div>
                            <div class="fs-row">
                                <span style="font-size:13px;">A</span>
                                <input type="range" id="fs-range" min="12" max="24" step="1" value="15">
                                <span style="font-size:22px;">A</span>
                                <span class="fs-val" id="fs-val">15 px</span>
                            </div>
                            <button class="opt-btn" style="flex:none;" onclick="setFont(15)" data-i18n="font_std">Стандартный (15)</button>
                        </div>

                        <div class="sp-card">
                            <div class="section-title" data-i18n="theme">Тема</div>
                            <div class="opt-row">
                                <button class="opt-btn" data-theme="dark" onclick="setTheme('dark')" data-i18n="dark">Чёрная</button>
                                <button class="opt-btn" data-theme="light" onclick="setTheme('light')" data-i18n="light">Белая</button>
                            </div>
                        </div>

                        <div class="sp-card">
                            <div class="section-title" data-i18n="colors">Цвета</div>
                            <div class="sub-label" data-i18n="bg_color">Цвет фона</div>
                            <div class="swatches" id="bg-swatches"></div>
                            <div class="sub-label" data-i18n="accent_color">Цвет акцента (кнопки и твои сообщения)</div>
                            <div class="swatches" id="accent-swatches"></div>
                            <button class="opt-btn" style="flex:none; margin-top:4px;" onclick="resetColors()" data-i18n="reset_colors">Сбросить цвета</button>
                        </div>

                        <div class="sp-card">
                            <div class="section-title" data-i18n="bg_title">Свой фон</div>
                            <div class="opt-desc" data-i18n="bg_desc">Можно выбрать фото из галереи или камеры. Фон один: новый заменяет старый.</div>
                            <div class="opt-desc" id="bg-status"></div>
                            <button class="opt-btn" style="flex:none;" onclick="pickBg()" data-i18n="bg_pick">Выбрать из галереи</button>
                            <button class="opt-btn" id="bg-tune-btn" style="flex:none; display:none;" onclick="tuneBg()" data-i18n="bg_tune">Яркость и размытие</button>
                            <button class="opt-btn btn-red" id="bg-del-btn" style="flex:none; display:none;" onclick="removeBg()" data-i18n="bg_del">Удалить фон</button>
                            <input type="file" id="bg-file" accept="image/*" style="display:none">
                        </div>

                        <div class="sp-card">
                            <div class="section-title" data-i18n="time_title">Время сообщений</div>
                            <div class="opt-row">
                                <button class="opt-btn" data-time="1" onclick="setShowTime(true)" data-i18n="time_on">Показывать</button>
                                <button class="opt-btn" data-time="0" onclick="setShowTime(false)" data-i18n="time_off">Скрыть</button>
                            </div>
                        </div>

                        <div class="sp-card">
                            <div class="section-title" data-i18n="gen">Генерация ответа</div>
                            <div class="opt-row">
                                <button class="opt-btn" data-anim="1" onclick="setAnimate(true)" data-i18n="anim_on">Анимация</button>
                                <button class="opt-btn" data-anim="0" onclick="setAnimate(false)" data-i18n="anim_off">Без анимации</button>
                            </div>
                            <div class="opt-desc" id="anim-desc"></div>
                        </div>
                    </div>

                    <div class="sp-pane" id="pane-account">
                        <div class="sp-card">
                            <div class="section-title" data-i18n="acc_title">Настройки аккаунта</div>
                            <div class="avatar-row">
                                <div class="avatar avatar-big" id="avatar-big"></div>
                                <div class="avatar-btns">
                                    <button class="opt-btn" onclick="pickAvatar()" data-i18n="avatar_pick">Выбрать фото</button>
                                    <button class="opt-btn" id="avatar-del-btn" onclick="removeAvatar()" data-i18n="avatar_del">Убрать фото</button>
                                </div>
                            </div>
                            <input type="file" id="avatar-file" accept="image/*" style="display:none">
                            <div class="sub-label" data-i18n="name_label">Твоё имя (Викед будет так к тебе обращаться)</div>
                            <input type="text" id="name-input" class="text-field" maxlength="30" placeholder="Как тебя зовут?" data-i18n-ph="name_ph" autocomplete="off">
                            <div class="sub-label" data-i18n="pron_label">Твои местоимения</div>
                            <select id="pron-select" class="text-field">
                                <option value="" data-i18n="pron_none">Не указывать</option>
                                <option value="f" data-i18n="pron_f">Она</option>
                                <option value="m" data-i18n="pron_m">Он</option>
                                <option value="n" data-i18n="pron_n">Они / нейтрально</option>
                            </select>
                            <div class="sub-label" data-i18n="about_label">О себе (необязательно)</div>
                            <textarea id="about-input" class="text-field" style="min-height:80px;" maxlength="300" placeholder="Например: люблю аниме, учусь в университете" data-i18n-ph="about_ph"></textarea>
                            <label class="check-row"><input type="checkbox" id="about-share"><span data-i18n="about_share">Показывать Викеду: он будет обращаться к тебе с учётом этого описания. Без галочки это просто твоя заметка.</span></label>
                        </div>
                        <div class="sp-card">
                            <button class="danger-btn" onclick="openDeleteConfirm()" data-i18n="del_acc">Удалить аккаунт</button>
                            <div class="opt-desc" data-i18n="del_acc_desc">Удалит все чаты, память и настройки.</div>
                        </div>
                        <div class="sp-card">
                            <div class="section-title" data-i18n="proto_title">Протокол Викеда</div>
                            <div class="opt-desc" data-i18n="proto_desc">Опиши характер Викеда строками вида «— строка». Он будет следовать им в каждом ответе.</div>
                            <textarea id="proto-input" class="text-field" maxlength="1500" spellcheck="false"></textarea>
                            <button class="opt-btn" style="flex:none;" onclick="resetProto()" data-i18n="proto_reset">Сбросить протокол</button>
                        </div>
                    </div>

                    <div class="sp-pane" id="pane-lang">
                        <div class="sp-card">
                            <div class="section-title" data-i18n="app_lang">Язык приложения</div>
                            <div class="opt-row">
                                <button class="opt-btn" data-lang="ru" onclick="setLang('ru')">Русский</button>
                                <button class="opt-btn" data-lang="en" onclick="setLang('en')">English</button>
                            </div>
                            <div class="opt-desc" data-i18n="app_lang_desc">Пока доступны русский и английский.</div>
                        </div>
                        <div class="sp-card">
                            <div class="section-title" data-i18n="bot_lang">Язык Викеда</div>
                            <select id="bot-lang" class="text-field"></select>
                            <div class="opt-desc" data-i18n="bot_lang_desc">На этом языке Викед будет отвечать тебе.</div>
                        </div>
                    </div>

                    <div class="opt-desc" style="text-align:center;" data-i18n="foot">Изменения вступят в силу только после нажатия ✓. Если выйти через ✖, они не сохранятся.</div>

                </div>
            </div>
        </div>
    </div>

    <!-- Подтверждение удаления аккаунта -->
    <div id="delete-page">
        <div class="confirm-title" data-i18n="confirm_title">Подтвердите.</div>
        <div class="confirm-text" data-i18n="confirm_text">Все чаты, память и настройки будут удалены без возможности восстановления.</div>
        <div class="confirm-box">
            <button class="danger-btn" id="delete-confirm-btn" disabled onclick="doDeleteAccount()"></button>
            <button class="opt-btn" style="flex:none;" onclick="closeDeleteConfirm()" data-i18n="cancel">Отмена</button>
        </div>
    </div>

    <!-- Загрузка -->
    <div id="loader-page"><div class="big-spinner"></div></div>

    <!-- Редактор фона -->
    <div id="bg-editor">
        <div id="bg-ed-img"></div>
        <div class="bg-ed-top">
            <span class="sp-x" onclick="cancelBgEditor()">✖</span>
            <span class="bg-ed-title" data-i18n="bg_ed_title">Предпросмотр фона</span>
            <span class="sp-ok" onclick="acceptBgEditor()">✓</span>
        </div>
        <div class="bg-ed-sample">
            <div class="message-wrapper bot"><div class="message" data-i18n="bg_sample_bot">Так выглядит чат на твоём фоне.</div></div>
            <div class="message-wrapper user"><div class="message" data-i18n="bg_sample_user">Выглядит отлично!</div></div>
        </div>
        <div class="bg-ed-panel">
            <div class="bg-ed-row"><span data-i18n="bright">Яркость</span><input type="range" id="bg-bright" min="20" max="100" step="1" value="100"><span class="fs-val" id="bg-bright-val">100%</span></div>
            <div class="bg-ed-row"><span data-i18n="blur">Размытие</span><input type="range" id="bg-blur" min="0" max="20" step="1" value="0"><span class="fs-val" id="bg-blur-val">0</span></div>
        </div>
    </div>

    <!-- Первый вход: имя -->
    <div id="welcome-screen">
        <div class="welcome-card">
            <div class="welcome-title" data-i18n="welcome_title">Привет! Я Викед.</div>
            <div class="opt-desc" style="font-size:15px;" data-i18n="welcome_q">Как тебя зовут?</div>
            <input type="text" id="welcome-name" class="text-field" maxlength="30" placeholder="Твоё имя" data-i18n-ph="welcome_ph" autocomplete="off">
            <button class="opt-btn active" style="flex:none;" onclick="submitWelcome()" data-i18n="welcome_btn">Продолжить ✓</button>
        </div>
    </div>

    <header>
        <div id="burger-btn" onclick="toggleSidebar()">☰</div>
        <div id="current-chat-title" onclick="scrollToFirst()" title="К первому сообщению" data-i18n-title="to_first">Викед</div>
        <div id="new-chat-top" onclick="newChatClick()" title="Новый чат" data-i18n-title="new_chat">
            <svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg" fill="none" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
                <path d="M4 4h16a1 1 0 0 1 1 1v11a1 1 0 0 1-1 1h-9l-5 4v-4H4a1 1 0 0 1-1-1V5a1 1 0 0 1 1-1z"/>
                <path d="M12 7.5v6M9 10.5h6"/>
            </svg>
        </div>
    </header>

    <div id="toast"></div>

    <div id="chat-wrap">
        <div id="chat-area"></div>
        <div id="scroll-down-btn" onmousedown="event.preventDefault()" onclick="scrollToBottom()" title="Вниз" data-i18n-title="down">
            <svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
                <path d="M12 5v14M5 12l7 7 7-7"/>
            </svg>
        </div>
    </div>

    <div id="ai-notice" data-i18n="ai_notice">Викед — ИИ, а не человек. Всё, что он пишет, вымышлено и не реально.</div>

    <div id="input-area">
        <input type="text" id="text-input" placeholder="Сообщение..." data-i18n-ph="input_ph" autocomplete="off" enterkeyhint="send">
        <!-- mousedown preventDefault: кнопка не забирает фокус, клавиатура остаётся открытой -->
        <button class="send-btn" id="send-btn" onmousedown="event.preventDefault()" onclick="onSendClick()">
            <svg class="ic-send" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
                <path d="M2.01 21L23 12 2.01 3 2 10l15 2-15 2z"/>
            </svg>
            <svg class="ic-stop" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg"><rect x="4" y="4" width="16" height="16" rx="2"/></svg>
        </button>
    </div>

    <script>
        const chatArea = document.getElementById('chat-area');
        const textInput = document.getElementById('text-input');
        const chatList = document.getElementById('chat-list');
        const currentTitle = document.getElementById('current-chat-title');
        const sidebar = document.getElementById('sidebar');
        const overlay = document.getElementById('overlay');
        const actionModal = document.getElementById('action-modal');
        const msgModal = document.getElementById('msg-modal');
        const settingsPage = document.getElementById('settings-page');
        const welcomeScreen = document.getElementById('welcome-screen');
        const scrollBtn = document.getElementById('scroll-down-btn');
        const nameInput = document.getElementById('name-input');
        const welcomeInput = document.getElementById('welcome-name');

        function clone(o) { return JSON.parse(JSON.stringify(o)); }


        // ---------- ЯЗЫКИ ИНТЕРФЕЙСА ----------
        const T = {
            ru: {
                chats: 'Мои чаты', settings: 'Настройки', rename: '✎ Переименовать', pin: '✪ Закрепить/Открепить', delete: '🗑️ Удалить', cancel: 'Отмена',
                edit: '✎ Изменить', copy: '❐ Копировать', exit_nosave: 'Выйти без сохранения', apply: 'Применить',
                tab_account: 'Аккаунт', tab_custom: 'Кастомизация', tab_lang: 'Язык', pick_section: 'Выбери раздел слева',
                theme: 'Тема', dark: 'Чёрная', light: 'Белая', preview: 'Предпросмотр', prev_user: 'Привет, Викед!',
                prev_bot: 'Это <b class="bold-text">действие</b> и <b class="big-text">крупный акцент</b>.',
                scale: 'Масштаб интерфейса', scale_desc: 'Одинаково на телефоне и на компьютере. Если всё кажется слишком крупным, уменьши.', scale_std: 'Стандартный (70%)',
                font: 'Размер шрифта', font_std: 'Стандартный (15)', colors: 'Цвета', bg_color: 'Цвет фона',
                accent_color: 'Цвет акцента (кнопки и твои сообщения)', reset_colors: 'Сбросить цвета', gen: 'Генерация ответа',
                anim_on: 'Анимация', anim_off: 'Без анимации',
                anim_on_desc: 'Сообщения появляются с анимацией, а ответ Викеда печатается на глазах.',
                anim_off_desc: 'Просто «Викед думает...», а потом сразу готовый ответ.',
                acc_title: 'Настройки аккаунта', name_label: 'Твоё имя (Викед будет так к тебе обращаться)', name_ph: 'Как тебя зовут?',
                del_acc: 'Удалить аккаунт', del_acc_desc: 'Удалит все чаты, память и настройки.',
                foot: 'Изменения вступят в силу только после нажатия ✓. Если выйти через ✖, они не сохранятся.',
                app_lang: 'Язык приложения', app_lang_desc: 'Пока доступны русский и английский.',
                bot_lang: 'Язык Викеда', bot_lang_desc: 'На этом языке Викед будет отвечать тебе.',
                confirm_title: 'Подтвердите.', confirm_text: 'Все чаты, память и настройки будут удалены без возможности восстановления.',
                del_wait: 'Удалить всё ({n})', del_yes: 'Да, удалить всё',
                welcome_title: 'Привет! Я Викед.', welcome_q: 'Как тебя зовут?', welcome_ph: 'Твоё имя', welcome_btn: 'Продолжить ✓',
                to_first: 'К первому сообщению', new_chat: 'Новый чат', down: 'Вниз',
                ai_notice: 'Викед — ИИ, а не человек. Всё, что он пишет, вымышлено и не реально.', input_ph: 'Сообщение...',
                no_chats: 'Нет сохраненных чатов', untitled: 'Без названия', enter_name: '⚠ Введи имя.', no_changes: 'Нет изменений.',
                applied: 'Изменения пришли в силу.', exit_confirm: '⚠ Изменения не будут применены. Выйти без сохранения?',
                hello_n: 'Привет, {n}! Я Викед. Чем займемся?', hello: 'Привет! Я Викед. Чем займемся?',
                rename_prompt: 'Введите новое название чата:', del_chat_confirm: 'Вы уверены, что хотите удалить этот чат?',
                already_new: 'Уже в новом чате.', wait_busy: 'Подожди, Викед отвечает.', thinking: 'Викед думает...', net_err: 'Ошибка сети.',
                regen: 'Перегенерировать', copy_title: 'Копировать', edit_prompt: 'Введите новый текст сообщения:',
                del_msg_confirm: 'Удалить это сообщение?', copied: 'Скопировано.', copy_fail: 'Не удалось скопировать.',
                regen_err: 'Ошибка сети при перегенерации', custom_color: 'Свой цвет',
                pron_label: 'Твои местоимения', pron_none: 'Не указывать', pron_f: 'Она', pron_m: 'Он', pron_n: 'Они / нейтрально',
                avatar_pick: 'Выбрать фото', avatar_del: 'Убрать фото', about_share: 'Показывать Викеду: он будет обращаться к тебе с учётом этого описания. Без галочки это просто твоя заметка.', about_label: 'О себе (необязательно)', about_ph: 'Например: люблю аниме, учусь в университете',
                proto_title: 'Протокол Викеда', proto_desc: 'Опиши характер Викеда строками вида «— строка». Он будет следовать им в каждом ответе.', proto_reset: 'Сбросить протокол',
                time_title: 'Время сообщений', time_on: 'Показывать', time_off: 'Скрыть',
                bg_title: 'Свой фон', bg_desc: 'Можно выбрать фото из галереи или камеры. Фон один: новый заменяет старый.',
                bg_pick: 'Выбрать из галереи', bg_tune: 'Яркость и размытие', bg_del: 'Удалить фон',
                bg_none: 'Фон не выбран.', bg_set: 'Фон установлен.', bg_ed_title: 'Предпросмотр фона', bright: 'Яркость', blur: 'Размытие',
                bg_sample_bot: 'Так выглядит чат на твоём фоне.', bg_sample_user: 'Выглядит отлично!',
                bg_saved: 'Фон применён.', bg_removed: 'Фон удалён.', bg_fail: 'Не удалось сохранить фон (слишком большой).', bg_err: 'Не удалось открыть картинку.',
                cont: '▶ Продолжить', stopped: 'Генерация остановлена.'
            },
            en: {
                chats: 'My chats', settings: 'Settings', rename: '✎ Rename', pin: '✪ Pin/Unpin', delete: '🗑️ Delete', cancel: 'Cancel',
                edit: '✎ Edit', copy: '❐ Copy', exit_nosave: 'Exit without saving', apply: 'Apply',
                tab_account: 'Account', tab_custom: 'Customize', tab_lang: 'Language', pick_section: 'Pick a section on the left',
                theme: 'Theme', dark: 'Dark', light: 'Light', preview: 'Preview', prev_user: 'Hi, Wicked!',
                prev_bot: 'This is an <b class="bold-text">action</b> and a <b class="big-text">big emphasis</b>.',
                scale: 'Interface scale', scale_desc: 'Same on phone and PC. If everything looks too big, lower it.', scale_std: 'Default (70%)',
                font: 'Font size', font_std: 'Default (15)', colors: 'Colors', bg_color: 'Background color',
                accent_color: 'Accent color (buttons and your messages)', reset_colors: 'Reset colors', gen: 'Reply generation',
                anim_on: 'Animation', anim_off: 'No animation',
                anim_on_desc: 'Messages appear with animation and the reply is typed out live.',
                anim_off_desc: 'Just "Wicked is thinking...", then the finished reply at once.',
                acc_title: 'Account settings', name_label: 'Your name (Wicked will call you that)', name_ph: "What's your name?",
                del_acc: 'Delete account', del_acc_desc: 'Deletes all chats, memory and settings.',
                foot: "Changes take effect only after pressing ✓. If you exit with ✖, they won't be saved.",
                app_lang: 'App language', app_lang_desc: 'Russian and English are available for now.',
                bot_lang: "Wicked's language", bot_lang_desc: 'Wicked will reply to you in this language.',
                confirm_title: 'Confirm.', confirm_text: 'All chats, memory and settings will be deleted permanently.',
                del_wait: 'Delete everything ({n})', del_yes: 'Yes, delete everything',
                welcome_title: "Hi! I'm Wicked.", welcome_q: "What's your name?", welcome_ph: 'Your name', welcome_btn: 'Continue ✓',
                to_first: 'To first message', new_chat: 'New chat', down: 'Down',
                ai_notice: 'Wicked is an AI, not a person. Everything it writes is fictional and not real.', input_ph: 'Message...',
                no_chats: 'No saved chats', untitled: 'Untitled', enter_name: '⚠ Enter your name.', no_changes: 'No changes.',
                applied: 'Changes applied.', exit_confirm: "⚠ Changes won't be applied. Exit without saving?",
                hello_n: "Hi, {n}! I'm Wicked. What shall we do?", hello: "Hi! I'm Wicked. What shall we do?",
                rename_prompt: 'Enter a new chat name:', del_chat_confirm: 'Are you sure you want to delete this chat?',
                already_new: 'Already in a new chat.', wait_busy: 'Wait, Wicked is replying.', thinking: 'Wicked is thinking...', net_err: 'Network error.',
                regen: 'Regenerate', copy_title: 'Copy', edit_prompt: 'Enter the new message text:',
                del_msg_confirm: 'Delete this message?', copied: 'Copied.', copy_fail: 'Copy failed.',
                regen_err: 'Network error while regenerating', custom_color: 'Custom color',
                pron_label: 'Your pronouns', pron_none: 'Not specified', pron_f: 'She / her', pron_m: 'He / him', pron_n: 'They / neutral',
                avatar_pick: 'Choose photo', avatar_del: 'Remove photo', about_share: 'Show to Wicked: he will address you based on this description. Unchecked, it is just your own note.', about_label: 'About me (optional)', about_ph: 'For example: I like anime, I study at university',
                proto_title: "Wicked's protocol", proto_desc: "Describe Wicked's character in lines like \"— line\". He will follow them in every reply.", proto_reset: 'Reset protocol',
                time_title: 'Message time', time_on: 'Show', time_off: 'Hide',
                bg_title: 'Custom background', bg_desc: 'Pick a photo from your gallery or camera. There is one background: a new one replaces the old.',
                bg_pick: 'Choose from gallery', bg_tune: 'Brightness and blur', bg_del: 'Remove background',
                bg_none: 'No background selected.', bg_set: 'Background is set.', bg_ed_title: 'Background preview', bright: 'Brightness', blur: 'Blur',
                bg_sample_bot: 'This is how the chat looks on your background.', bg_sample_user: 'Looks great!',
                bg_saved: 'Background applied.', bg_removed: 'Background removed.', bg_fail: "Couldn't save the background (too large).", bg_err: "Couldn't open the image.",
                cont: '▶ Continue', stopped: 'Generation stopped.'
            }
        };
        const BOT_LANGS = [
            ['ru', 'Русский'], ['en', 'English'], ['uk', 'Українська'], ['de', 'Deutsch'], ['es', 'Español'], ['fr', 'Français'],
            ['it', 'Italiano'], ['pt', 'Português'], ['tr', 'Türkçe'], ['zh', '中文'], ['ja', '日本語'], ['ko', '한국어'], ['ar', 'العربية']
        ];
        let curLang = 'ru';
        function t(k, vars) {
            let v = (T[curLang] && T[curLang][k]) || T.ru[k] || k;
            if (vars) for (const x in vars) v = v.replace('{' + x + '}', vars[x]);
            return v;
        }
        function applyLang(l) {
            curLang = T[l] ? l : 'ru';
            document.documentElement.lang = curLang;
            document.querySelectorAll('[data-i18n]').forEach(e => { e.textContent = t(e.dataset.i18n); });
            document.querySelectorAll('[data-i18n-html]').forEach(e => { e.innerHTML = t(e.dataset.i18nHtml); });
            document.querySelectorAll('[data-i18n-ph]').forEach(e => { e.placeholder = t(e.dataset.i18nPh); });
            document.querySelectorAll('[data-i18n-title]').forEach(e => { e.title = t(e.dataset.i18nTitle); });
        }

        // ---------- БАЗА ЧАТОВ ----------
        let db = { chats: [], activeId: null };
        try {
            let saved = JSON.parse(localStorage.getItem('wicked_chats_v8'));
            if (saved && Array.isArray(saved.chats)) { db = saved; }
        } catch (e) {}
        // Старые чаты не переименовываем автоматически
        db.chats.forEach(c => { if (c.titled === undefined) c.titled = true; });

        let activeModalChatId = null;
        let activeMsgIndex = null;
        let busy = false;
        let abortCtl = null;
        let typingCtl = null;
        const sendBtn = document.getElementById('send-btn');
        function setSendBtn() { sendBtn.classList.toggle('stopping', !!busy); }
        function fmtTime(ts) {
            return new Date(ts).toLocaleTimeString(curLang === 'en' ? 'en-US' : 'ru-RU', { hour: '2-digit', minute: '2-digit' });
        }

        function saveDB() { localStorage.setItem('wicked_chats_v8', JSON.stringify(db)); }

        function normMsg(m) {
            if (!m.variants) {
                m.variants = [m.text || ''];
                m.currentVariant = 0;
            }
            if (typeof m.currentVariant !== 'number') m.currentVariant = 0;
            if (m.sender === 'user') {
                // tails[i] — «хвост» переписки (ответы после сообщения) для версии i
                if (!m.tails) m.tails = [];
                while (m.tails.length < m.variants.length) m.tails.push([]);
            }
            return m;
        }
        function getText(m) { normMsg(m); return m.variants[m.currentVariant]; }
        function activeChat() { return db.chats.find(c => c.id === db.activeId); }

        textInput.addEventListener('keypress', function (e) { if (e.key === 'Enter') { e.preventDefault(); sendMessage(); } });

        // ---------- ПРОКРУТКА ----------
        function nearBottom(limit) {
            return chatArea.scrollHeight - chatArea.scrollTop - chatArea.clientHeight < (limit || 120);
        }
        function updateScrollBtn() {
            scrollBtn.classList.toggle('show', !nearBottom(200));
        }
        chatArea.addEventListener('scroll', updateScrollBtn, { passive: true });

        function scrollToFirst() {
            chatArea.scrollTo({ top: 0, behavior: 'smooth' });
        }
        function scrollToBottom() {
            chatArea.scrollTo({ top: chatArea.scrollHeight, behavior: 'smooth' });
        }

        // ---------- ФОРМАТИРОВАНИЕ **жирный** ----------
        function buildSegments(text) {
            const segs = [];
            // **"текст"** — крупный акцент, **текст** — действие (серый жирный)
            const re = /\*\*["“«]([\s\S]+?)["”»]\*\*|\*\*([\s\S]+?)\*\*/g;
            let last = 0, m;
            while ((m = re.exec(text)) !== null) {
                if (m.index > last) segs.push({ t: text.slice(last, m.index), k: 'n' });
                if (m[1] !== undefined) segs.push({ t: m[1], k: 'big' });
                else segs.push({ t: m[2], k: 'b' });
                last = re.lastIndex;
            }
            if (last < text.length) segs.push({ t: text.slice(last), k: 'n' });
            return segs;
        }

        function fillFormatted(el, text, limit) {
            el.textContent = '';
            let left = (limit === undefined) ? Infinity : limit;
            buildSegments(text).forEach(sg => {
                if (left <= 0) return;
                const piece = sg.t.slice(0, left);
                left -= piece.length;
                if (sg.k === 'n') {
                    el.appendChild(document.createTextNode(piece));
                } else {
                    const b = document.createElement('b');
                    b.className = sg.k === 'big' ? 'big-text' : 'bold-text';
                    b.textContent = piece;
                    el.appendChild(b);
                }
            });
        }

        // Печать текста по буквам. Возвращает объект управления (stop() останавливает печать).
        function typeFormatted(el, text, onDone, startAt) {
            startAt = startAt || 0;
            const segs = buildSegments(text);
            el.textContent = '';
            const nodes = segs.map(sg => {
                let n;
                if (sg.k === 'n') n = document.createElement('span');
                else { n = document.createElement('b'); n.className = sg.k === 'big' ? 'big-text' : 'bold-text'; }
                el.appendChild(n);
                return n;
            });
            const total = segs.reduce((a, sg) => a + sg.t.length, 0);
            const ctl = { total: total, shown: startAt, cancelled: false, stop: function () { this.cancelled = true; return this.shown; } };
            function paint(shown) {
                for (let i = 0; i < segs.length; i++) {
                    const take = Math.max(0, Math.min(segs[i].t.length, shown));
                    nodes[i].textContent = segs[i].t.slice(0, take);
                    shown -= take;
                }
            }
            paint(startAt);
            const duration = Math.min(Math.max((total - startAt) * 18, 400), 5000);
            const start = performance.now();
            function step(now) {
                if (ctl.cancelled) return;
                if (!el.isConnected) { if (onDone) onDone(true); return; }
                const stick = nearBottom(150); // если читаешь выше — не дёргаем вниз
                const p = Math.min(1, (now - start) / duration);
                ctl.shown = startAt + Math.floor((total - startAt) * p);
                paint(ctl.shown);
                if (stick) chatArea.scrollTop = chatArea.scrollHeight;
                if (p < 1) requestAnimationFrame(step);
                else if (onDone) onDone(false);
            }
            requestAnimationFrame(step);
            return ctl;
        }

        function stripBold(text) {
            return text.replace(/\*\*["“«]([\s\S]+?)["”»]\*\*/g, '$1').replace(/\*\*/g, '');
        }

        // ---------- НАСТРОЙКИ ----------
        const DEFAULTS = {
            dark:  { bg: '#0e1621', accent: '#5288c1' },
            light: { bg: '#eef1f5', accent: '#3a7bd5' }
        };
        const BG_PRESETS = {
            dark:  ['#0e1621', '#000000', '#121212', '#1a1423', '#0f1f17', '#1f1414', '#101a2e'],
            light: ['#eef1f5', '#ffffff', '#fff7e6', '#eaf6ee', '#f6ecf7', '#e8f1fb', '#fbeaea']
        };
        const ACCENT_PRESETS = ['#5288c1', '#3a7bd5', '#e74c3c', '#2ecc71', '#9b59b6', '#f39c12', '#1abc9c', '#e91e63'];

        // settings — то, что реально применено и сохранено. draft — черновик на странице настроек.
        const DEFAULT_PROTO = {
            ru: 'Викед.\n— Обычный ИИ-помощник: спокойный, вежливый, по делу.',
            en: 'Wicked.\n— A regular AI assistant: calm, polite, to the point.'
        };
        function defaultSettings() {
            return { name: '', theme: 'dark', animate: true, fontSize: 15, uiScale: 70, lang: 'ru', botLang: 'ru',
                showTime: true, pronouns: '', about: '', aboutShare: true, avatar: '', protocol: DEFAULT_PROTO.ru,
                bg: { on: false, bright: 100, blur: 0 },
                custom: { dark: { bg: null, accent: null }, light: { bg: null, accent: null } } };
        }
        let settings = defaultSettings();
        try {
            const s = JSON.parse(localStorage.getItem('wicked_settings'));
            if (s && (s.theme === 'dark' || s.theme === 'light')) {
                settings.theme = s.theme;
                if (typeof s.name === 'string') settings.name = s.name;
                if (typeof s.animate === 'boolean') settings.animate = s.animate;
                if (s.lang && T[s.lang]) settings.lang = s.lang;
                if (s.botLang && BOT_LANGS.some(x => x[0] === s.botLang)) settings.botLang = s.botLang;
                if (typeof s.showTime === 'boolean') settings.showTime = s.showTime;
                if (['', 'f', 'm', 'n'].indexOf(s.pronouns) >= 0) settings.pronouns = s.pronouns;
                if (typeof s.aboutShare === 'boolean') settings.aboutShare = s.aboutShare;
                if (typeof s.avatar === 'string' && s.avatar.indexOf('data:image/') === 0 && s.avatar.length < 300000) settings.avatar = s.avatar;
                if (typeof s.about === 'string') settings.about = s.about.slice(0, 300);
                if (typeof s.protocol === 'string') settings.protocol = s.protocol.slice(0, 1500);
                if (s.bg && typeof s.bg === 'object') settings.bg = { on: !!s.bg.on, bright: Math.min(100, Math.max(20, +s.bg.bright || 100)), blur: Math.min(20, Math.max(0, +s.bg.blur || 0)) };
                if (typeof s.uiScale === 'number') settings.uiScale = Math.min(110, Math.max(50, Math.round(s.uiScale)));
                if (typeof s.fontSize === 'number') settings.fontSize = Math.min(24, Math.max(12, Math.round(s.fontSize)));
                if (s.custom) {
                    ['dark', 'light'].forEach(t => {
                        if (s.custom[t]) settings.custom[t] = { bg: s.custom[t].bg || null, accent: s.custom[t].accent || null };
                    });
                }
            }
        } catch (e) {}
        let draft = clone(settings);

        function saveSettings() { localStorage.setItem('wicked_settings', JSON.stringify(settings)); }

        function hexToRgb(h) {
            h = h.replace('#', '');
            if (h.length === 3) h = h.split('').map(c => c + c).join('');
            const n = parseInt(h, 16);
            return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
        }
        function rgbToHex(r, g, b) {
            return '#' + [r, g, b].map(v => Math.round(Math.max(0, Math.min(255, v))).toString(16).padStart(2, '0')).join('');
        }
        function mix(a, b, t) {
            const A = hexToRgb(a), B = hexToRgb(b);
            return rgbToHex(A[0] + (B[0] - A[0]) * t, A[1] + (B[1] - A[1]) * t, A[2] + (B[2] - A[2]) * t);
        }
        function lum(h) { const c = hexToRgb(h); return (0.299 * c[0] + 0.587 * c[1] + 0.114 * c[2]) / 255; }

        function currentColors(src) {
            const d = DEFAULTS[src.theme];
            const c = src.custom[src.theme];
            return { bg: c.bg || d.bg, accent: c.accent || d.accent };
        }

        let curScale = 70;
        function applyScale(pct) {
            curScale = pct;
            const k = pct / 100;
            document.body.style.zoom = k;
            document.body.style.height = (window.innerHeight / k) + 'px';
        }
        window.addEventListener('resize', () => applyScale(curScale));

        function applyTheme(src) {
            const col = currentColors(src);
            const bg = col.bg, accent = col.accent;
            const light = lum(bg) > 0.55;
            const r = document.documentElement.style;
            r.setProperty('--fs', (src.fontSize || 15) + 'px');
            applyScale(src.uiScale || 70);
            r.setProperty('--bg', bg);
            r.setProperty('--accent', accent);
            r.setProperty('--text', light ? '#111111' : '#ffffff');
            r.setProperty('--muted', light ? '#6b7785' : '#7d8b99');
            r.setProperty('--bold', light ? '#555d66' : '#b5bcc6');
            r.setProperty('--panel', light ? mix(bg, '#ffffff', 0.7) : mix(bg, '#ffffff', 0.06));
            r.setProperty('--msg-bot', light ? mix(bg, '#ffffff', 0.85) : mix(bg, '#ffffff', 0.08));
            r.setProperty('--msg-user', light ? mix(accent, '#ffffff', 0.7) : mix(accent, '#000000', 0.45));
            r.setProperty('--border', light ? mix(bg, '#000000', 0.12) : mix(bg, '#000000', 0.4));
            r.setProperty('--hover', light ? mix(bg, '#000000', 0.07) : mix(bg, '#ffffff', 0.1));
            r.setProperty('--overlay', light ? 'rgba(0,0,0,0.35)' : 'rgba(0,0,0,0.6)');
        }

        function buildSwatches(containerId, list, current, key) {
            const box = document.getElementById(containerId);
            box.innerHTML = '';
            list.forEach(colr => {
                const s = document.createElement('div');
                s.className = 'swatch' + (colr.toLowerCase() === current.toLowerCase() ? ' active' : '');
                s.style.background = colr;
                s.addEventListener('click', () => setColor(key, colr));
                box.appendChild(s);
            });
            const inp = document.createElement('input');
            inp.type = 'color';
            inp.value = current;
            inp.title = t('custom_color');
            inp.addEventListener('input', () => {
                draft.custom[draft.theme][key] = inp.value;
                applyTheme(draft);
            });
            inp.addEventListener('change', renderSettings);
            box.appendChild(inp);
        }

        function renderSettings() {
            document.querySelectorAll('[data-theme]').forEach(b => b.classList.toggle('active', b.dataset.theme === draft.theme));
            document.querySelectorAll('[data-anim]').forEach(b => b.classList.toggle('active', (b.dataset.anim === '1') === draft.animate));
            document.getElementById('anim-desc').textContent = draft.animate ? t('anim_on_desc') : t('anim_off_desc');
            document.querySelectorAll('[data-lang]').forEach(b => b.classList.toggle('active', b.dataset.lang === draft.lang));
            document.getElementById('bot-lang').value = draft.botLang;
            document.querySelectorAll('[data-time]').forEach(b => b.classList.toggle('active', (b.dataset.time === '1') === draft.showTime));
            renderAvatar(document.getElementById('avatar-big'), draft.avatar, nameInput.value || draft.name);
            document.getElementById('avatar-del-btn').style.display = draft.avatar ? '' : 'none';
            document.querySelectorAll('.prev-time').forEach(e => { e.style.display = draft.showTime ? '' : 'none'; });
            updateBgUi();
            const fr = document.getElementById('fs-range');
            fr.value = draft.fontSize;
            document.getElementById('sc-range').value = draft.uiScale;
            document.getElementById('sc-val').textContent = draft.uiScale + '%';
            document.getElementById('fs-val').textContent = draft.fontSize + ' px';
            const cur = currentColors(draft);
            buildSwatches('bg-swatches', BG_PRESETS[draft.theme], cur.bg, 'bg');
            buildSwatches('accent-swatches', ACCENT_PRESETS, cur.accent, 'accent');
        }

        // Изменения на странице настроек идут в черновик и сразу видны, но сохраняются только по ✓
        function setColor(key, val) {
            draft.custom[draft.theme][key] = val;
            applyTheme(draft); renderSettings();
        }
        function setTheme(t) {
            draft.theme = t;
            applyTheme(draft); renderSettings();
        }
        function resetColors() {
            draft.custom[draft.theme] = { bg: null, accent: null };
            applyTheme(draft); renderSettings();
        }
        function setFont(v) {
            draft.fontSize = Math.min(24, Math.max(12, Math.round(v)));
            applyTheme(draft); renderSettings();
        }
        document.getElementById('fs-range').addEventListener('input', function () {
            draft.fontSize = parseInt(this.value, 10);
            document.getElementById('fs-val').textContent = draft.fontSize + ' px';
            applyTheme(draft);
        });
        function setScale(v) {
            draft.uiScale = Math.min(110, Math.max(50, Math.round(v)));
            applyTheme(draft); renderSettings();
        }
        document.getElementById('sc-range').addEventListener('input', function () {
            draft.uiScale = parseInt(this.value, 10);
            document.getElementById('sc-val').textContent = draft.uiScale + '%';
            applyTheme(draft);
        });
        // ---------- АВАТАР И НИК ----------
        function renderAvatar(el, src, name) {
            if (src) { el.style.backgroundImage = 'url("' + src + '")'; el.textContent = ''; }
            else { el.style.backgroundImage = 'none'; el.textContent = (name || '?').trim().charAt(0).toUpperCase() || '?'; }
        }
        function updateBadge() {
            renderAvatar(document.getElementById('avatar-sm'), settings.avatar, settings.name);
            document.getElementById('profile-name').textContent = settings.name || '';
        }
        const avatarFile = document.getElementById('avatar-file');
        const aboutShare = document.getElementById('about-share');
        aboutShare.addEventListener('change', () => { draft.aboutShare = aboutShare.checked; });
        function pickAvatar() { avatarFile.click(); }
        function removeAvatar() { draft.avatar = ''; renderSettings(); }
        avatarFile.addEventListener('change', () => {
            const f = avatarFile.files && avatarFile.files[0];
            avatarFile.value = '';
            if (!f) return;
            const reader = new FileReader();
            reader.onload = () => {
                const img = new Image();
                img.onload = () => {
                    const size = 256;
                    const c = document.createElement('canvas');
                    c.width = size; c.height = size;
                    const m = Math.min(img.width, img.height);
                    c.getContext('2d').drawImage(img, (img.width - m) / 2, (img.height - m) / 2, m, m, 0, 0, size, size);
                    draft.avatar = c.toDataURL('image/jpeg', 0.85);
                    renderSettings();
                };
                img.onerror = () => showToast(t('bg_err'));
                img.src = reader.result;
            };
            reader.readAsDataURL(f);
        });
        function setShowTime(v) { draft.showTime = v; renderSettings(); }
        const pronSelect = document.getElementById('pron-select');
        const aboutInput = document.getElementById('about-input');
        const protoInput = document.getElementById('proto-input');
        pronSelect.addEventListener('change', () => { draft.pronouns = pronSelect.value; });
        aboutInput.addEventListener('input', () => { draft.about = aboutInput.value; });
        protoInput.addEventListener('input', () => { draft.protocol = protoInput.value; });
        function resetProto() {
            draft.protocol = DEFAULT_PROTO[curLang] || DEFAULT_PROTO.ru;
            protoInput.value = draft.protocol;
        }
        function setLang(l) {
            draft.lang = l;
            applyLang(l);
            renderSettings();
        }
        (function () {
            const sel = document.getElementById('bot-lang');
            BOT_LANGS.forEach(x => { const o = document.createElement('option'); o.value = x[0]; o.textContent = x[1]; sel.appendChild(o); });
            sel.addEventListener('change', () => { draft.botLang = sel.value; });
        })();
        function setAnimate(v) {
            draft.animate = v;
            renderSettings();
        }
        nameInput.addEventListener('input', () => { draft.name = nameInput.value; });

        function isDirty() { return JSON.stringify(draft) !== JSON.stringify(settings); }

        function setTab(t) {
            document.querySelectorAll('.sp-tab').forEach(b => b.classList.toggle('active', b.dataset.tab === t));
            document.querySelectorAll('.sp-pane').forEach(p => p.classList.toggle('active', p.id === 'pane-' + t));
            document.getElementById('sp-body').classList.toggle('nothing', !t);
            document.getElementById('sp-body').scrollTop = 0;
        }

        function openSettings() {
            closeAllModals();
            setTab(null);
            draft = clone(settings);
            nameInput.value = draft.name;
            pronSelect.value = draft.pronouns || '';
            aboutInput.value = draft.about || '';
            aboutShare.checked = draft.aboutShare !== false;
            protoInput.value = draft.protocol || '';
            renderSettings();
            settingsPage.classList.add('open');
        }

        // ✖ — выйти без применения
        function cancelSettings() {
            if (isDirty()) {
                if (!confirm(t('exit_confirm'))) return;
            }
            draft = clone(settings);
            applyTheme(settings); // откатываем предпросмотр
            applyLang(settings.lang);
            settingsPage.classList.remove('open');
        }

        // ✓ — применить
        function applySettings() {
            const nm = (draft.name || '').trim();
            if (!nm) {
                setTab('account');
                showToast(t('enter_name'));
                nameInput.focus();
                return;
            }
            draft.name = nm;
            draft.about = (draft.about || '').trim();
            draft.protocol = (draft.protocol || '').trim().slice(0, 1500);
            if (!isDirty()) {
                settingsPage.classList.remove('open');
                showToast(t('no_changes'));
                return;
            }
            const nameChanged = nm !== settings.name || draft.lang !== settings.lang;
            const timeChanged = draft.showTime !== settings.showTime;
            settings = clone(draft);
            try { saveSettings(); } catch (e) { showToast(t('bg_fail')); }
            updateBadge();
            applyTheme(settings);
            settingsPage.classList.remove('open');
            if (nameChanged) refreshWelcome();
            if (timeChanged && activeChat()) openChat(db.activeId);
            showToast(t('applied'));
        }

        applyTheme(settings);
        applyLang(settings.lang);
        updateBadge();

        // ---------- ПЕРВЫЙ ВХОД / ПРИВЕТСТВИЕ ----------
        function welcomeText() {
            return settings.name ? t('hello_n', { n: settings.name }) : t('hello');
        }

        function refreshWelcome() {
            const chat = activeChat();
            if (!chat) createNewChat();
            else if (chat.messages.length === 0) openChat(chat.id);
        }

        function showWelcomeScreen() {
            welcomeScreen.classList.add('open');
            setTimeout(() => welcomeInput.focus(), 100);
        }

        function submitWelcome() {
            const name = welcomeInput.value.trim();
            if (!name) { showToast(t('enter_name')); return; }
            settings.name = name;
            saveSettings();
            updateBadge();
            draft = clone(settings);
            welcomeScreen.classList.remove('open');
            refreshWelcome();
        }
        welcomeInput.addEventListener('keypress', function (e) { if (e.key === 'Enter') { e.preventDefault(); submitWelcome(); } });

        // ---------- СВОЙ ФОН ----------
        let bgData = null;
        try { bgData = localStorage.getItem('wicked_bg'); } catch (e) {}
        const bgLayer = document.getElementById('bg-layer');
        const bgEditor = document.getElementById('bg-editor');
        const bgEdImg = document.getElementById('bg-ed-img');
        const bgBright = document.getElementById('bg-bright');
        const bgBlur = document.getElementById('bg-blur');
        const bgFile = document.getElementById('bg-file');
        let edData = null;

        function bgFilter(b, bl) { return 'brightness(' + b + '%) blur(' + bl + 'px)'; }
        function applyBg() {
            if (settings.bg && settings.bg.on && bgData) {
                bgLayer.style.backgroundImage = 'url("' + bgData + '")';
                bgLayer.style.filter = bgFilter(settings.bg.bright, settings.bg.blur);
                bgLayer.style.display = 'block';
            } else {
                bgLayer.style.display = 'none';
                bgLayer.style.backgroundImage = 'none';
            }
            updateBgUi();
        }
        function updateBgUi() {
            const has = !!(settings.bg && settings.bg.on && bgData);
            document.getElementById('bg-tune-btn').style.display = has ? '' : 'none';
            document.getElementById('bg-del-btn').style.display = has ? '' : 'none';
            document.getElementById('bg-status').textContent = has ? t('bg_set') : t('bg_none');
        }
        function pickBg() { bgFile.click(); }
        bgFile.addEventListener('change', () => {
            const f = bgFile.files && bgFile.files[0];
            bgFile.value = '';
            if (!f) return;
            const reader = new FileReader();
            reader.onload = () => {
                const img = new Image();
                img.onload = () => {
                    const k = Math.min(1, 1400 / Math.max(img.width, img.height));
                    const w = Math.max(1, Math.round(img.width * k)), h = Math.max(1, Math.round(img.height * k));
                    const c = document.createElement('canvas');
                    c.width = w; c.height = h;
                    c.getContext('2d').drawImage(img, 0, 0, w, h);
                    openBgEditor(c.toDataURL('image/jpeg', 0.82), 100, 0);
                };
                img.onerror = () => showToast(t('bg_err'));
                img.src = reader.result;
            };
            reader.onerror = () => showToast(t('bg_err'));
            reader.readAsDataURL(f);
        });
        function updateEd() {
            bgEdImg.style.filter = bgFilter(bgBright.value, bgBlur.value);
            document.getElementById('bg-bright-val').textContent = bgBright.value + '%';
            document.getElementById('bg-blur-val').textContent = bgBlur.value;
        }
        bgBright.addEventListener('input', updateEd);
        bgBlur.addEventListener('input', updateEd);
        function openBgEditor(data, bright, blur) {
            edData = data;
            bgEdImg.style.backgroundImage = 'url("' + data + '")';
            bgBright.value = bright; bgBlur.value = blur;
            updateEd();
            bgEditor.classList.add('open');
        }
        function tuneBg() { if (bgData) openBgEditor(bgData, settings.bg.bright, settings.bg.blur); }
        function cancelBgEditor() { edData = null; bgEditor.classList.remove('open'); }
        function acceptBgEditor() {
            if (!edData) { cancelBgEditor(); return; }
            try { localStorage.setItem('wicked_bg', edData); }
            catch (e) { showToast(t('bg_fail')); return; }
            bgData = edData;
            settings.bg = { on: true, bright: parseInt(bgBright.value, 10), blur: parseInt(bgBlur.value, 10) };
            draft.bg = clone(settings.bg);
            saveSettings();
            applyBg();
            cancelBgEditor();
            showToast(t('bg_saved'));
        }
        function removeBg() {
            try { localStorage.removeItem('wicked_bg'); } catch (e) {}
            bgData = null;
            settings.bg = { on: false, bright: 100, blur: 0 };
            draft.bg = clone(settings.bg);
            saveSettings();
            applyBg();
            showToast(t('bg_removed'));
        }
        applyBg();

        // ---------- УДАЛЕНИЕ АККАУНТА ----------
        const deletePage = document.getElementById('delete-page');
        const deleteBtn = document.getElementById('delete-confirm-btn');
        const loaderPage = document.getElementById('loader-page');
        let deleteTimer = null;

        function openDeleteConfirm() {
            deletePage.classList.add('open');
            let n = 5;
            deleteBtn.disabled = true;
            deleteBtn.textContent = t('del_wait', { n: n });
            clearInterval(deleteTimer);
            deleteTimer = setInterval(() => {
                n--;
                if (n <= 0) {
                    clearInterval(deleteTimer);
                    deleteBtn.disabled = false;
                    deleteBtn.textContent = t('del_yes');
                } else {
                    deleteBtn.textContent = t('del_wait', { n: n });
                }
            }, 1000);
        }
        function closeDeleteConfirm() {
            clearInterval(deleteTimer);
            deletePage.classList.remove('open');
        }
        function doDeleteAccount() {
            if (deleteBtn.disabled) return;
            clearInterval(deleteTimer);
            deletePage.classList.remove('open');
            loaderPage.classList.add('open');
            setTimeout(() => {
                try {
                    Object.keys(localStorage).filter(k => k.indexOf('wicked_') === 0).forEach(k => localStorage.removeItem(k));
                } catch (e) {}
                db = { chats: [], activeId: null };
                settings = defaultSettings();
                bgData = null;
                applyBg();
                draft = clone(settings);
                applyTheme(settings);
                applyLang(settings.lang);
                updateBadge();
                chatArea.innerHTML = '';
                currentTitle.innerText = 'Викед';
                settingsPage.classList.remove('open');
                closeAllModals();
                loaderPage.classList.remove('open');
                showWelcomeScreen();
            }, 1800);
        }

        // ---------- МЕНЮ И ОКНА ----------
        // ---------- СВАЙП ОТ ЛЕВОГО КРАЯ ----------
        (function () {
            let sx = 0, sy = 0, mode = null;
            function blocked() {
                return ['settings-page', 'welcome-screen', 'delete-page', 'bg-editor', 'loader-page'].some(id => document.getElementById(id).classList.contains('open'));
            }
            document.addEventListener('touchstart', e => {
                const tc = e.touches[0];
                sx = tc.clientX; sy = tc.clientY; mode = null;
                if (blocked()) return;
                if (sidebar.classList.contains('open')) mode = 'close';
                else if (sx <= 45) mode = 'open';
            }, { passive: true });
            document.addEventListener('touchmove', e => {
                if (!mode) return;
                const tc = e.touches[0];
                const dx = tc.clientX - sx, dy = tc.clientY - sy;
                if (Math.abs(dx) < 50 || Math.abs(dx) < Math.abs(dy) * 1.5) return;
                if (mode === 'open' && dx > 0) { mode = null; if (!sidebar.classList.contains('open')) toggleSidebar(); }
                else if (mode === 'close' && dx < 0) { mode = null; closeAllModals(); }
            }, { passive: true });
        })();

        // ---------- НЕ ДАТЬ СТРАНИЦЕ «ОБНОВЛЯТЬСЯ» ПРИ СВАЙПЕ ВНИЗ ----------
        // Документ чуть длиннее экрана и всегда прокручен на 1px: тогда pull-to-refresh (в браузере и в APK) не срабатывает.
        (function () {
            const pad = document.createElement('div');
            pad.id = 'ptr-pad';
            document.documentElement.appendChild(pad);
            function lock() { if (window.scrollY < 1) window.scrollTo(0, 1); }
            window.addEventListener('scroll', lock, { passive: true });
            window.addEventListener('load', lock);
            window.addEventListener('resize', lock);
            setTimeout(lock, 200); setTimeout(lock, 800);
        })();

        function toggleSidebar() {
            if (sidebar.classList.contains('open')) {
                closeAllModals();
            } else {
                sidebar.classList.add('open');
                overlay.classList.add('open');
                renderChatList();
            }
        }

        function closeActionModal() {
            actionModal.classList.remove('open');
            activeModalChatId = null;
        }

        function closeMsgModal() {
            msgModal.classList.remove('open');
            overlay.classList.remove('open');
            activeMsgIndex = null;
        }

        function closeAllModals() {
            actionModal.classList.remove('open');
            msgModal.classList.remove('open');
            sidebar.classList.remove('open');
            overlay.classList.remove('open');
            activeModalChatId = null;
            activeMsgIndex = null;
        }

        // Долгое нажатие (800 мс на чатах, 600 мс на сообщениях)
        function attachLongPress(el, handler, onTap, delay) {
            let timer = null, fired = false;
            const start = () => {
                clearTimeout(timer);
                fired = false;
                timer = setTimeout(() => { fired = true; handler(); }, delay || 600);
            };
            const cancel = () => clearTimeout(timer);
            el.addEventListener('mousedown', start);
            el.addEventListener('touchstart', start, { passive: true });
            ['mouseup', 'mouseleave', 'touchend', 'touchmove', 'touchcancel'].forEach(ev =>
                el.addEventListener(ev, cancel, { passive: true }));
            el.addEventListener('contextmenu', e => e.preventDefault());
            el.addEventListener('click', e => {
                if (fired) { fired = false; e.preventDefault(); return; }
                if (onTap) onTap();
            });
        }

        // ---------- ЧАТЫ ----------
        function renderChatList() {
            chatList.innerHTML = '';
            if (db.chats.length === 0) {
                chatList.innerHTML = '<div style="text-align:center; color:var(--muted); margin-top:20px; font-size:14px;">' + t('no_chats') + '</div>';
                return;
            }

            const sortedChats = [...db.chats].sort((a, b) => {
                if (a.pinned && !b.pinned) return -1;
                if (!a.pinned && b.pinned) return 1;
                return b.timestamp - a.timestamp;
            });

            sortedChats.forEach(chat => {
                const div = document.createElement('div');
                div.className = 'chat-item' + (chat.id === db.activeId ? ' active' : '');
                const dateStr = new Date(chat.timestamp).toLocaleDateString('ru-RU', { hour: '2-digit', minute: '2-digit' });

                if (chat.pinned) {
                    const pin = document.createElement('div');
                    pin.className = 'pin-icon';
                    pin.textContent = '✪';
                    div.appendChild(pin);
                }
                const t = document.createElement('div');
                t.className = 'chat-item-title';
                t.textContent = chat.title || t('untitled');
                const d = document.createElement('div');
                d.className = 'chat-item-date';
                d.textContent = dateStr;
                div.appendChild(t);
                div.appendChild(d);

                attachLongPress(div, () => openActionModal(chat.id, chat.title), () => openChat(chat.id), 800);
                chatList.appendChild(div);
            });
        }

        function openActionModal(chatId, title) {
            activeModalChatId = chatId;
            document.getElementById('modal-chat-title').innerText = title;
            actionModal.classList.add('open');
            overlay.classList.add('open');
        }

        function renameChat() {
            const chat = db.chats.find(c => c.id === activeModalChatId);
            if (!chat) return;
            const newTitle = prompt(t('rename_prompt'), chat.title);
            if (newTitle && newTitle.trim() !== "") {
                chat.title = newTitle.trim();
                chat.renamed = true; // ручное название — автоназвание больше не трогает
                if (db.activeId === chat.id) currentTitle.innerText = chat.title;
                saveDB();
            }
            closeActionModal();
            renderChatList();
        }

        function pinChat() {
            const chat = db.chats.find(c => c.id === activeModalChatId);
            if (!chat) return;
            chat.pinned = !chat.pinned;
            saveDB();
            closeActionModal();
            renderChatList();
        }

        function deleteChat() {
            const id = activeModalChatId;
            if (confirm(t('del_chat_confirm'))) {
                db.chats = db.chats.filter(c => c.id !== id);
                if (db.activeId === id) {
                    db.activeId = null;
                    chatArea.innerHTML = '';
                    currentTitle.innerText = 'Викед';
                    showWelcomeCard();
                }
                saveDB();
            }
            closeActionModal();
            renderChatList();
        }

        function openChat(id, animIdx) {
            const chat = db.chats.find(c => c.id === id);
            if (!chat) return;

            if (typingCtl) { typingCtl.cancelled = true; typingCtl = null; busy = false; setSendBtn(); }
            db.activeId = id;
            saveDB();
            currentTitle.innerText = chat.title;
            chatArea.innerHTML = '';

            if (chat.messages.length === 0) {
                showWelcomeCard();
            }
            chat.messages.forEach((msg, index) => renderMessage(msg, index, index === animIdx));

            closeAllModals();
            chatArea.scrollTop = chatArea.scrollHeight;
            updateScrollBtn();
        }

        let toastTimer;
        function showToast(text) {
            const t = document.getElementById('toast');
            t.textContent = text;
            t.classList.add('show');
            clearTimeout(toastTimer);
            toastTimer = setTimeout(() => t.classList.remove('show'), 2200);
        }

        function newChatClick() {
            const chat = activeChat();
            if (!db.activeId || !chat || chat.messages.length === 0) {
                showToast(t('already_new'));
                return;
            }
            createNewChat();
        }

        function showWelcomeCard() {
            const d = document.createElement('div');
            d.className = 'welcome-center';
            d.textContent = welcomeText();
            chatArea.appendChild(d);
        }

        function createNewChat() {
            db.activeId = null; saveDB();
            chatArea.innerHTML = '';
            currentTitle.innerText = 'Викед';
            showWelcomeCard();
            closeAllModals();
            updateScrollBtn();
        }

        // ---------- АВТОНАЗВАНИЕ ЧАТА ----------
        function cleanTitle(t, fallback) {
            t = (t || '').replace(/[*"«»“”'`#]/g, '').replace(/[.!?…,;:\s]+$/, '').trim();
            const words = t.split(/\s+/).filter(Boolean).slice(0, 4);
            if (!words.length) return fallback;
            let r = words.join(' ');
            if (r.length > 40) r = r.slice(0, 40).trim();
            return r.charAt(0).toUpperCase() + r.slice(1);
        }
        function fallbackTitle(text) {
            return cleanTitle(stripBold(text).split(/\s+/).slice(0, 4).join(' '), t('new_chat'));
        }

        async function maybeAutoTitle(chat) {
            if (chat.titled || chat.renamed) return;
            const u = chat.messages.find(m => m.sender === 'user');
            const b = chat.messages.find(m => m.sender === 'bot');
            if (!u || !b) return;
            chat.titled = true;
            saveDB();
            try {
                const r = await fetch('/title', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ user: getText(u), bot: getText(b), bot_lang: settings.botLang })
                });
                const d = await r.json();
                if (chat.renamed || !db.chats.includes(chat)) return;
                chat.title = cleanTitle(d.title, fallbackTitle(getText(u)));
                saveDB();
                if (db.activeId === chat.id) currentTitle.innerText = chat.title;
                if (sidebar.classList.contains('open')) renderChatList();
            } catch (e) {
                chat.titled = false;
            }
        }

        // ---------- ИСТОРИЯ ДЛЯ СЕРВЕРА ----------
        function getChatHistoryText(chat, upTo) {
            let text = "";
            const limit = (upTo === undefined) ? chat.messages.length : upTo;
            for (let i = 0; i < limit; i++) {
                const m = chat.messages[i];
                if (m.aborted) continue;
                if (m.sender === 'user') text += 'Пользователь: ' + getText(m) + '\n';
                else text += 'Викед: ' + getText(m) + '\n';
            }
            return text;
        }

        // ---------- ОТПРАВКА ----------
        async function sendMessage() {
            const text = textInput.value.trim();
            if (!text) return;
            if (busy) { showToast(t('wait_busy')); return; }

            if (!db.activeId || !activeChat()) {
                const newChat = {
                    id: Date.now().toString(),
                    title: fallbackTitle(text),
                    timestamp: Date.now(),
                    messages: [],
                    pinned: false,
                    titled: false,
                    renamed: false
                };
                db.chats.push(newChat);
                db.activeId = newChat.id;
                currentTitle.innerText = newChat.title;
                chatArea.innerHTML = '';
            }

            const currentChat = activeChat();
            const historyBefore = getChatHistoryText(currentChat);
            const userMsg = { sender: 'user', text: text, variants: [text], currentVariant: 0, tails: [[]], ts: Date.now() };
            currentChat.messages.push(userMsg);
            renderMessage(userMsg, currentChat.messages.length - 1, true);
            textInput.value = '';
            textInput.focus(); // клавиатура остаётся открытой
            currentChat.timestamp = Date.now();
            saveDB();

            await generateBotResponse(currentChat, text, historyBefore);
        }

        function timeInfo() {
            const now = new Date();
            return {
                time24: now.toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' }),
                time12: now.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', hour12: true })
            };
        }

        async function askServer(promptText, historyText, signal) {
            const t = timeInfo();
            const response = await fetch('/chat', {
                method: 'POST',
                signal: signal,
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    message: promptText,
                    time24: t.time24,
                    time12: t.time12,
                    memory: localStorage.getItem('wicked_memory') || "Пока нет информации.",
                    history: historyText,
                    user_name: settings.name,
                    bot_lang: settings.botLang,
                    ui_lang: settings.lang,
                    pronouns: settings.pronouns,
                    about: settings.aboutShare ? settings.about : '',
                    protocol: settings.protocol
                })
            });
            return await response.json();
        }

        async function generateBotResponse(currentChat, promptText, historyText) {
            busy = true;
            setSendBtn();
            abortCtl = new AbortController();
            const wrapper = document.createElement('div');
            wrapper.className = 'message-wrapper bot';
            wrapper.innerHTML = '<div class="status"><div class="spinner"></div> ' + t('thinking') + '</div>';
            chatArea.appendChild(wrapper);
            chatArea.scrollTop = chatArea.scrollHeight;

            let ok = false;
            try {
                const data = await askServer(promptText, historyText, abortCtl.signal);
                if (wrapper.parentNode) wrapper.parentNode.removeChild(wrapper);

                // Чат мог быть удалён, пока шёл запрос
                if (db.chats.includes(currentChat)) {
                    const newBotMsg = {
                        sender: 'bot',
                        variants: [data.reply],
                        currentVariant: 0,
                        status: data.status,
                        ts: Date.now()
                    };
                    currentChat.messages.push(newBotMsg);
                    saveDB();
                    if (db.activeId === currentChat.id) {
                        renderMessage(newBotMsg, currentChat.messages.length - 1, true);
                    }
                    ok = data.status !== 'Ошибка';
                }
                if (data.new_memory) localStorage.setItem('wicked_memory', data.new_memory);
            } catch (error) {
                if (wrapper.parentNode) wrapper.parentNode.removeChild(wrapper);
                if (error && error.name === 'AbortError') {
                    // Остановлено до ответа: оставляем пустое сообщение с кнопкой «Продолжить»
                    if (db.chats.includes(currentChat)) {
                        const stoppedMsg = { sender: 'bot', variants: [''], currentVariant: 0, status: '', aborted: true, ts: Date.now() };
                        currentChat.messages.push(stoppedMsg);
                        saveDB();
                        if (db.activeId === currentChat.id) renderMessage(stoppedMsg, currentChat.messages.length - 1, false);
                    }
                } else {
                    const errDiv = document.createElement('div');
                    errDiv.className = 'message-wrapper bot';
                    errDiv.innerHTML = '<div class="message">' + t('net_err') + '</div>';
                    chatArea.appendChild(errDiv);
                }
            }
            abortCtl = null;
            if (!typingCtl) { busy = false; setSendBtn(); }
            chatArea.scrollTop = chatArea.scrollHeight;
            if (ok) maybeAutoTitle(currentChat);
        }

        function onSendClick() {
            if (busy) stopGeneration();
            else sendMessage();
        }

        // ■ — остановить генерацию
        function stopGeneration() {
            if (typingCtl) {
                const ctl = typingCtl;
                typingCtl = null;
                const shown = ctl.stop();
                busy = false;
                setSendBtn();
                if (shown < ctl.total) { ctl.msg.cut = shown; saveDB(); }
                if (activeChat()) openChat(db.activeId);
                return;
            }
            if (abortCtl) abortCtl.abort();
        }

        // ▶ — продолжить остановленную генерацию
        function continueGen(idx) {
            if (busy) { showToast(t('wait_busy')); return; }
            const chat = activeChat();
            if (!chat) return;
            const msg = chat.messages[idx];
            if (!msg) return;
            if (msg.aborted) {
                let u = -1;
                for (let i = idx - 1; i >= 0; i--) { if (chat.messages[i].sender === 'user') { u = i; break; } }
                if (u < 0) return;
                const promptText = getText(chat.messages[u]);
                chat.messages.splice(idx, 1);
                saveDB();
                openChat(db.activeId);
                generateBotResponse(chat, promptText, getChatHistoryText(chat, u));
                return;
            }
            if (typeof msg.cut === 'number') {
                if (!settings.animate) { delete msg.cut; saveDB(); openChat(db.activeId); return; }
                openChat(db.activeId, idx);
            }
        }

        // ---------- СООБЩЕНИЯ ----------
        function renderMessage(msg, msgIndex, animate) {
            normMsg(msg);
            const anim = !!animate && settings.animate;
            const wrapper = document.createElement('div');
            wrapper.className = 'message-wrapper ' + msg.sender + (anim ? ' anim-in' : '');

            if (msg.sender === 'bot') {
                const statusDiv = document.createElement('div');
                statusDiv.className = 'status';
                statusDiv.innerHTML = msg.status || '';
                if (!msg.status) statusDiv.style.display = 'none';
                wrapper.appendChild(statusDiv);
            }

            const msgDiv = document.createElement('div');
            msgDiv.className = 'message';
            attachLongPress(msgDiv, () => openMsgModal(msgIndex), null, 600);
            wrapper.appendChild(msgDiv);

            if (settings.showTime && msg.ts) {
                const tm = document.createElement('div');
                tm.className = 'msg-time';
                tm.textContent = fmtTime(msg.ts);
                wrapper.appendChild(tm);
            }
            chatArea.appendChild(wrapper);

            const needControls = msg.sender === 'bot' || msg.variants.length > 1;
            const addControls = () => {
                if (needControls) wrapper.appendChild(buildControls(msg, msgIndex));
                if (nearBottom(200)) chatArea.scrollTop = chatArea.scrollHeight;
                updateScrollBtn();
            };

            if (msg.sender === 'bot' && msg.aborted) {
                msgDiv.classList.add('msg-stopped');
                msgDiv.textContent = '■ ' + t('stopped');
                addControls();
            } else if (anim && msg.sender === 'bot') {
                const start = (typeof msg.cut === 'number') ? msg.cut : 0;
                busy = true;
                setSendBtn();
                const ctl = typeFormatted(msgDiv, getText(msg), (abandoned) => {
                    if (typingCtl === ctl) typingCtl = null;
                    busy = false;
                    setSendBtn();
                    if (abandoned) return;
                    if (msg.cut !== undefined) { delete msg.cut; saveDB(); }
                    addControls();
                }, start);
                ctl.msg = msg;
                typingCtl = ctl;
            } else {
                fillFormatted(msgDiv, getText(msg), (typeof msg.cut === 'number') ? msg.cut : undefined);
                addControls();
            }
            chatArea.scrollTop = chatArea.scrollHeight;
        }

        function buildControls(msg, msgIndex) {
            const controls = document.createElement('div');
            controls.className = 'msg-controls';

            const total = msg.variants.length;

            const prev = document.createElement('span');
            prev.textContent = '<';
            if (msg.currentVariant === 0) prev.className = 'disabled';
            prev.addEventListener('click', () => changeVariant(msgIndex, -1));

            const counter = document.createElement('span');
            counter.textContent = (msg.currentVariant + 1) + '/' + total;
            counter.style.cursor = 'default';

            const next = document.createElement('span');
            next.textContent = '>';
            if (msg.currentVariant === total - 1) next.className = 'disabled';
            next.addEventListener('click', () => changeVariant(msgIndex, 1));

            if (msg.sender === 'bot' && (msg.aborted || typeof msg.cut === 'number')) {
                const chatNow = activeChat();
                if (chatNow && msgIndex === chatNow.messages.length - 1) {
                    const cb = document.createElement('span');
                    cb.className = 'cont-btn';
                    cb.textContent = t('cont');
                    cb.addEventListener('click', () => continueGen(msgIndex));
                    controls.appendChild(cb);
                }
            }
            if (msg.aborted) return controls;

            controls.appendChild(prev);
            controls.appendChild(counter);
            controls.appendChild(next);

            if (msg.sender === 'bot') {
                const regen = document.createElement('span');
                regen.textContent = '↻';
                regen.title = t('regen');
                regen.style.cssText = 'font-size:16px; margin-left:5px;';
                regen.addEventListener('click', () => regenerate(msgIndex, regen));

                const copyBtn = document.createElement('span');
                copyBtn.textContent = '❐';
                copyBtn.title = t('copy_title');
                copyBtn.style.cssText = 'font-size:16px; margin-left:5px;';
                copyBtn.addEventListener('click', () => copyToClipboard(stripBold(getText(msg)), copyBtn));

                controls.appendChild(regen);
                controls.appendChild(copyBtn);
            }
            return controls;
        }

        function changeVariant(msgIndex, direction) {
            if (busy) { showToast(t('wait_busy')); return; }
            const chat = activeChat();
            if (!chat) return;
            const msg = normMsg(chat.messages[msgIndex]);

            const old = msg.currentVariant;
            let nw = old;
            if (direction === -1 && old > 0) nw = old - 1;
            else if (direction === 1 && old < msg.variants.length - 1) nw = old + 1;
            else return;

            delete msg.cut;
            if (msg.sender === 'user') {
                // Переключаем ветку: убираем текущий хвост переписки и подставляем хвост выбранной версии
                msg.tails[old] = chat.messages.splice(msgIndex + 1);
                msg.currentVariant = nw;
                msg.text = msg.variants[nw];
                const tail = msg.tails[nw] || [];
                msg.tails[nw] = [];
                tail.forEach(m => chat.messages.push(m));
            } else {
                msg.currentVariant = nw;
            }

            saveDB();
            openChat(db.activeId);
        }

        // Окно действий с сообщением
        function openMsgModal(index) {
            const chat = activeChat();
            if (!chat) return;
            const msg = chat.messages[index];
            if (!msg) return;
            activeMsgIndex = index;
            let snippet = stripBold(getText(msg));
            if (snippet.length > 40) snippet = snippet.substring(0, 40) + '...';
            document.getElementById('msg-modal-title').innerText = snippet;
            document.getElementById('msg-edit-btn').style.display = msg.sender === 'user' ? 'block' : 'none';
            msgModal.classList.add('open');
            overlay.classList.add('open');
        }

        async function editMessage() {
            if (busy) { closeMsgModal(); showToast(t('wait_busy')); return; }
            const chat = activeChat();
            const idx = activeMsgIndex;
            if (!chat || idx === null) return;
            const msg = normMsg(chat.messages[idx]);
            if (!msg || msg.sender !== 'user') return;

            const oldText = getText(msg);
            const newText = prompt(t('edit_prompt'), oldText);
            if (!newText || newText.trim() === "" || newText.trim() === oldText) {
                closeMsgModal();
                return;
            }
            const nt = newText.trim();

            // Старая ветка (с ответами) сохраняется, начинается новая
            msg.tails[msg.currentVariant] = chat.messages.splice(idx + 1);
            msg.variants.push(nt);
            msg.tails.push([]);
            msg.currentVariant = msg.variants.length - 1;
            msg.text = nt;
            chat.timestamp = Date.now();
            saveDB();

            closeMsgModal();
            openChat(db.activeId);
            // ИИ отвечает на изменённое сообщение
            await generateBotResponse(chat, nt, getChatHistoryText(chat, idx));
        }

        function deleteMessage() {
            if (busy) { closeMsgModal(); showToast(t('wait_busy')); return; }
            const chat = activeChat();
            const idx = activeMsgIndex;
            if (!chat || idx === null) return;
            if (confirm(t('del_msg_confirm'))) {
                chat.messages.splice(idx, 1);
                saveDB();
                closeMsgModal();
                openChat(db.activeId);
                return;
            }
            closeMsgModal();
        }

        function copyMessageFromModal() {
            const chat = activeChat();
            if (!chat || activeMsgIndex === null) return;
            const text = stripBold(getText(chat.messages[activeMsgIndex]));
            copyText(text).then(ok => {
                closeMsgModal();
                showToast(ok ? t('copied') : t('copy_fail'));
            });
        }

        // ---------- ПЕРЕГЕНЕРАЦИЯ ----------
        async function regenerate(msgIndex, element) {
            if (busy) { showToast(t('wait_busy')); return; }
            const chat = activeChat();
            if (!chat) return;

            let userIdx = -1;
            for (let i = msgIndex - 1; i >= 0; i--) {
                if (chat.messages[i].sender === 'user') { userIdx = i; break; }
            }
            if (userIdx < 0) return;
            const userPrompt = getText(chat.messages[userIdx]);

            busy = true;
            setSendBtn();
            abortCtl = new AbortController();
            element.style.pointerEvents = 'none';
            element.innerHTML = '<span class="loading-dots"></span>';

            try {
                const data = await askServer(userPrompt, getChatHistoryText(chat, userIdx), abortCtl.signal);

                const m = normMsg(chat.messages[msgIndex]);
                m.variants.push(data.reply);
                m.currentVariant = m.variants.length - 1;
                m.status = data.status;
                delete m.cut;
                saveDB();

                if (data.new_memory) localStorage.setItem('wicked_memory', data.new_memory);
                abortCtl = null;
                busy = false;
                setSendBtn();
                openChat(db.activeId, msgIndex);
            } catch (error) {
                abortCtl = null;
                busy = false;
                setSendBtn();
                element.innerText = '↻';
                element.style.pointerEvents = 'auto';
                if (!(error && error.name === 'AbortError')) alert(t('regen_err'));
            }
        }

        // ---------- КОПИРОВАНИЕ ----------
        function fallbackCopy(text) {
            const ta = document.createElement('textarea');
            ta.value = text;
            ta.style.cssText = 'position:fixed; top:0; left:0; opacity:0;';
            document.body.appendChild(ta);
            ta.focus();
            ta.select();
            ta.setSelectionRange(0, text.length);
            let ok = false;
            try { ok = document.execCommand('copy'); } catch (e) {}
            document.body.removeChild(ta);
            return ok;
        }

        async function copyText(text) {
            let ok = false;
            // navigator.clipboard работает только по HTTPS/localhost, поэтому есть запасной способ
            if (navigator.clipboard && window.isSecureContext) {
                try { await navigator.clipboard.writeText(text); ok = true; } catch (e) {}
            }
            if (!ok) ok = fallbackCopy(text);
            return ok;
        }

        async function copyToClipboard(text, element) {
            const ok = await copyText(text);
            element.innerText = ok ? '✔' : '✖';
            element.style.color = ok ? '#4CAF50' : '#e74c3c';
            setTimeout(() => {
                element.innerText = '❐';
                element.style.color = '';
            }, 1500);
        }

        // Простое сообщение без управления (приветствие)
        function addMessageToDOM(text, sender) {
            const wrapper = document.createElement('div');
            wrapper.className = 'message-wrapper ' + sender;
            const msgDiv = document.createElement('div');
            msgDiv.className = 'message';
            msgDiv.textContent = text;
            wrapper.appendChild(msgDiv);
            chatArea.appendChild(wrapper);
            chatArea.scrollTop = chatArea.scrollHeight;
        }

        // При каждом запуске открывается новый пустой чат, а прошлые остаются в меню чатов
        createNewChat();
        if (!settings.name) showWelcomeScreen();
    </script>
</body>
</html>
"""


@app.route('/')
def home():
    return HTML_PAGE


@app.route('/health')
def health():
    return 'ok'


@app.route('/title', methods=['POST'])
def make_title():
    data = request.get_json(force=True)
    user_text = (data.get('user') or '')[:600]
    bot_text = (data.get('bot') or '')[:600]
    title = ''
    try:
        title = llm_small([
            {"role": "system", "content": "Придумай короткое название чата по первому сообщению пользователя и ответу. Строго от 1 до 4 слов, на языке: " + LANGS.get(data.get("bot_lang"), "русский") + ", по смыслу темы, без кавычек, без точки в конце, без эмодзи. Пример: пользователь спросил, что делать если телефон не включается — название «Проблема телефона». Выведи ТОЛЬКО название."},
            {"role": "user", "content": f"Сообщение: {user_text}\n\nОтвет: {bot_text}"}
        ], temperature=0.3, max_tokens=30)
    except Exception:
        pass
    title = title.strip().split("\n")[0] if title else ''
    return jsonify({"title": title})


@app.route('/chat', methods=['POST'])
def chat():
    data = request.get_json(force=True)
    user_message = data.get('message', '')
    time24 = data.get('time24', 'Неизвестно')
    time12 = data.get('time12', 'Неизвестно')
    memory = data.get('memory', 'Пока нет информации.')
    chat_history_text = data.get('history', '') or ''
    user_name = (data.get('user_name') or '').strip()[:30]
    bot_lang = data.get('bot_lang') or 'ru'
    pronouns = data.get('pronouns') or ''
    about = (data.get('about') or '').strip()[:300]
    protocol = (data.get('protocol') or '').strip()[:1500]
    lang_name = LANGS.get(bot_lang, 'русский')
    M = MSG.get(data.get('ui_lang'), MSG['ru'])

    # 1. Фоновое обновление долговременной памяти
    new_memory = memory
    try:
        if len(user_message.strip()) < 25:
            raise ValueError('short')
        mem = llm_small([
            {"role": "system", "content": "Ты — ассистент, который ведет блокнот памяти пользователя. Прочитай текущую память и последнее сообщение. Если есть важные факты (имя, возраст, хобби), добавь их. Если фактов нет, верни память без изменений. Пиши кратко."},
            {"role": "user", "content": f"Текущая память:\n{memory}\n\nСообщение: {user_message}"}
        ], temperature=0.1, max_tokens=400).strip()
        if mem:
            new_memory = mem
    except Exception:
        pass

    # 2. Контекст: память + история + время + имя
    name_line = f"\n\n12. Пользователя зовут {user_name}. Обращайся к нему по имени естественно, но не в каждом сообщении." if user_name else ""
    extra_lines = ""
    if pronouns == 'f':
        extra_lines += "\n\n15. Пользователь — женского рода (местоимения она/её). Обращайся к нему в женском роде."
    elif pronouns == 'm':
        extra_lines += "\n\n15. Пользователь — мужского рода (местоимения он/его). Обращайся к нему в мужском роде."
    elif pronouns == 'n':
        extra_lines += "\n\n15. Пользователь предпочитает нейтральные местоимения (они/их). Избегай указания рода, используй нейтральные формулировки."
    if about:
        extra_lines += "\n\n16. Пользователь о себе (учитывай это): " + about
    if protocol:
        extra_lines += ("\n\n14. ПРОТОКОЛ ХАРАКТЕРА, который задал пользователь. Строки с «—» описывают характер, тон и поведение Викеда. "
                        "Следуй им в каждом ответе:\n" + protocol)
    system_content = f"""{base_prompt}

8. ВАЖНО: Твоя долговременная память о пользователе (факты из прошлых чатов):
{new_memory}

9. ВАЖНО: История вашего текущего диалога (читай это, если спрашивают, о чем вы говорили или что было раньше):
{chat_history_text}

10. Текущее время: {time24} (в 12-часовом формате: {time12}). Если спросят время, используй эти данные.{name_line}{extra_lines}

13. ЯЗЫК ОТВЕТОВ: всегда отвечай на языке: {lang_name}, даже если пользователь пишет на другом, пока он сам не попросит сменить язык."""

    try:
        answer = llm([
            {"role": "system", "content": system_content},
            {"role": "user", "content": user_message}
        ], temperature=0.7)

        m = re.search(r"SEARCH:\s*[\"'«]?(.+?)[\"'»]?\s*(?:\n|$)", answer)
        if m:
            query = m.group(1).strip()
            found = get_wikipedia_text(query) or web_search(query)
            safe_query = query.replace("<", "&lt;").replace(">", "&gt;")

            if found:
                system_content += ("\n\n11. РЕЗУЛЬТАТЫ ПОИСКА В ИНТЕРНЕТЕ (используй их для ответа). "
                                   "Ответь на вопрос пользователя СРАЗУ, полным ответом, в этом же сообщении. "
                                   "Не пиши слово SEARCH и не говори, что сейчас поищешь. Отвечай на языке: " + lang_name + ":\n" + found)
                status_text = f"<span style='color:#5288c1'>🔍 Поиск: {safe_query}</span>"
            else:
                system_content += ("\n\n11. Поиск в интернете ничего не дал. Ответь на вопрос пользователя СРАЗУ, "
                                   "как можешь, по своим знаниям, коротко отметив, что не уверен в свежести данных. "
                                   "Не пиши слово SEARCH.")
                status_text = "<span style='color:#e74c3c'>" + M["nosearch"] + "</span>"

            final_answer = llm([
                {"role": "system", "content": system_content},
                {"role": "user", "content": user_message}
            ], temperature=0.3)
            final_answer = re.sub(r"SEARCH:.*", "", final_answer).strip() or M["noans"]
            return jsonify({"status": status_text, "reply": final_answer, "new_memory": new_memory})

        return jsonify({"status": "", "reply": answer, "new_memory": new_memory})

    except Exception as e:
        if "No route to host" in str(e):
            return jsonify({"status": "", "reply": M["offline"], "new_memory": new_memory})
        return jsonify({"status": "Ошибка", "reply": f"Ошибка: {e}", "new_memory": new_memory})


if __name__ == '__main__':
    # PORT задаёт хостинг; локально по умолчанию 8080
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 8080)))
