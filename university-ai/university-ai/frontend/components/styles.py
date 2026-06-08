"""
frontend/components/styles.py
═════════════════════════════
CSS premium partajat între toate paginile (look SaaS modern, dark).

Folosim Streamlit `st.markdown(..., unsafe_allow_html=True)` pentru injecție.
Definim variabile CSS (--primary, --bg-card etc.) ca să fie ușor de re-tematizat.

IMPORTANT: acest fișier conține DOAR stiluri (zero logică de aplicație). Toate
clasele folosite de view-uri (`.hero-title`, `.feature-card`, `.source-badge`,
`.status-pill`, `.auth-container`, `.user-chip` etc.) sunt păstrate — aici doar
le rafinăm aspectul și adăugăm stiluri pentru componentele native Streamlit
(chat bubbles, sidebar, formulare, butoane).
"""

import streamlit as st


# ── Paleta + variabile globale ────────────────────────────────────────────────

GLOBAL_CSS = """
<style>
:root {
    --primary: #6366f1;
    --primary-light: #818cf8;
    --primary-dark: #4f46e5;
    --accent: #a855f7;
    --pink: #ec4899;
    --success: #34d399;
    --warning: #f59e0b;
    --danger: #f43f5e;

    --bg-deep: #0a0e1a;
    --bg-card: #141a2a;
    --bg-card-hover: #1b2236;
    --bg-elevated: #1f2740;
    --border: rgba(255,255,255,0.08);
    --border-strong: rgba(255,255,255,0.16);

    --text-primary: #f3f5fa;
    --text-secondary: #b8c2d6;
    --text-muted: #7d8aa0;

    --radius: 16px;
    --radius-sm: 10px;
    --shadow-sm: 0 1px 3px rgba(0,0,0,0.25);
    --shadow-md: 0 6px 20px rgba(0,0,0,0.30);
    --shadow-lg: 0 24px 48px rgba(0,0,0,0.40);
    --shadow-glow: 0 8px 30px rgba(99,102,241,0.30);

    --gradient-hero: linear-gradient(135deg, #6366f1 0%, #a855f7 50%, #ec4899 100%);
    --gradient-card: linear-gradient(135deg, rgba(99,102,241,0.10), rgba(168,85,247,0.05));
    --font-sans: -apple-system, BlinkMacSystemFont, "Segoe UI", "Inter", Roboto,
                 "Helvetica Neue", Arial, sans-serif;
}

/* ═══ APP BACKGROUND (gradient subtil) ═══ */
.stApp {
    background:
        radial-gradient(1200px 600px at 12% -5%, rgba(99,102,241,0.12), transparent 60%),
        radial-gradient(1000px 500px at 100% 0%, rgba(168,85,247,0.10), transparent 55%),
        var(--bg-deep);
    color: var(--text-primary);
    font-family: var(--font-sans);
}

.main .block-container {
    padding-top: 2.2rem;
    max-width: 1200px;
}

[data-testid="stHeader"] { background: transparent; }

/* ═══ TIPOGRAFIE ═══ */
html, body, [class*="css"] { font-family: var(--font-sans); }
h1, h2, h3, h4 {
    letter-spacing: -0.02em;
    color: var(--text-primary);
}
p, li, span, label { color: var(--text-secondary); }

/* ═══ BUTOANE ═══ */
.stButton > button,
.stFormSubmitButton > button {
    border-radius: var(--radius-sm);
    font-weight: 600;
    padding: 0.55rem 1rem;
    transition: transform 0.18s ease, box-shadow 0.18s ease, background 0.18s ease, border-color 0.18s ease;
    border: 1px solid var(--border-strong);
    background: rgba(255,255,255,0.03);
    color: var(--text-primary);
}
.stButton > button:hover,
.stFormSubmitButton > button:hover {
    transform: translateY(-1px);
    border-color: var(--primary-light);
    background: rgba(255,255,255,0.06);
}
.stButton > button[kind="primary"],
.stFormSubmitButton > button[kind="primary"] {
    background: linear-gradient(135deg, var(--primary), var(--accent));
    border: none;
    color: #fff;
    box-shadow: var(--shadow-glow);
}
.stButton > button[kind="primary"]:hover,
.stFormSubmitButton > button[kind="primary"]:hover {
    transform: translateY(-2px);
    box-shadow: 0 12px 34px rgba(99,102,241,0.45);
}

/* ═══ INPUTS ═══ */
.stTextInput input,
.stTextArea textarea,
section[data-testid="stChatInput"] textarea {
    border-radius: var(--radius-sm) !important;
    border: 1px solid var(--border) !important;
    background: rgba(255,255,255,0.03) !important;
    transition: border-color 0.15s, box-shadow 0.15s !important;
}
.stTextInput input:focus,
.stTextArea textarea:focus,
section[data-testid="stChatInput"] textarea:focus {
    border-color: var(--primary) !important;
    box-shadow: 0 0 0 3px rgba(99,102,241,0.18) !important;
}

/* ═══ CHAT INPUT BAR ═══ */
section[data-testid="stChatInput"] {
    border-radius: 14px !important;
    border: 1px solid var(--border) !important;
    background: var(--bg-card) !important;
    box-shadow: var(--shadow-md);
}

/* ═══ CHAT BUBBLES ═══ */
[data-testid="stChatMessage"] {
    background: var(--bg-card);
    border: 1px solid var(--border);
    border-radius: 18px;
    padding: 14px 18px;
    margin-bottom: 14px;
    box-shadow: var(--shadow-sm);
}
/* mesajele utilizatorului — accent indigo */
[data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarUser"]) {
    background: linear-gradient(135deg, rgba(99,102,241,0.16), rgba(168,85,247,0.08));
    border-color: rgba(99,102,241,0.35);
}
[data-testid="stChatMessage"] p { color: var(--text-primary); }

/* ═══ BADGE-URI & CHIPS ═══ */
.source-badge {
    background: linear-gradient(135deg, rgba(52,211,153,0.14), rgba(16,185,129,0.06));
    color: #7ff0c0;
    border: 1px solid rgba(52,211,153,0.35);
    padding: 5px 13px;
    border-radius: 16px;
    font-size: 0.80em;
    margin: 3px 4px 3px 0;
    display: inline-block;
    font-family: 'SF Mono', Consolas, monospace;
    box-shadow: var(--shadow-sm);
}
.score-chip {
    background: linear-gradient(135deg, rgba(99,102,241,0.16), rgba(79,70,229,0.06));
    color: #aeb8ff;
    border: 1px solid rgba(99,102,241,0.35);
    padding: 2px 8px;
    border-radius: 10px;
    font-size: 0.72em;
    margin-left: 6px;
}
.rerank-chip {
    background: linear-gradient(135deg, rgba(168,85,247,0.16), rgba(124,58,237,0.06));
    color: #d6b4fe;
    border: 1px solid rgba(168,85,247,0.35);
    padding: 2px 8px;
    border-radius: 10px;
    font-size: 0.72em;
}
.ocr-chip {
    background: linear-gradient(135deg, rgba(245,158,11,0.16), rgba(217,119,6,0.06));
    color: #fcd34d;
    border: 1px solid rgba(245,158,11,0.35);
    padding: 2px 8px;
    border-radius: 10px;
    font-size: 0.70em;
    font-weight: 600;
}

/* ═══ STATUS PILLS ═══ */
.status-pill {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    padding: 5px 14px;
    border-radius: 20px;
    background: rgba(255,255,255,0.04);
    border: 1px solid var(--border);
    font-size: 0.85em;
    color: var(--text-secondary);
}
.status-dot {
    width: 8px; height: 8px;
    border-radius: 50%;
    animation: pulse 2s infinite;
}
.status-dot.ok  { background: var(--success); box-shadow: 0 0 8px var(--success); }
.status-dot.err { background: var(--danger); }
.status-dot.warn { background: var(--warning); }

@keyframes pulse {
    0%, 100% { opacity: 1; }
    50% { opacity: 0.5; }
}

/* ═══ CITATION / SOURCE CARDS ═══ */
.citation-block {
    background: rgba(99,102,241,0.06);
    border-left: 3px solid var(--primary);
    padding: 12px 16px;
    margin: 8px 0;
    border-radius: 0 10px 10px 0;
    font-size: 0.88em;
    color: var(--text-secondary);
}

/* expander (surse / fragmente) ca un card elegant */
[data-testid="stExpander"] {
    border: 1px solid var(--border) !important;
    border-radius: var(--radius) !important;
    background: var(--bg-card) !important;
    box-shadow: var(--shadow-sm);
    overflow: hidden;
}
[data-testid="stExpander"] summary:hover { color: var(--primary-light); }

/* ═══ THINKING ANIMATION ═══ */
.thinking {
    display: inline-block;
    color: var(--text-muted);
    font-style: italic;
}
.thinking::after {
    content: '';
    animation: dots 1.5s steps(4, end) infinite;
}
@keyframes dots {
    0%, 20% { content: ''; }
    40% { content: '.'; }
    60% { content: '..'; }
    80%, 100% { content: '...'; }
}

/* ═══ NAVBAR + BRAND ═══ */
.brand {
    display: flex;
    align-items: center;
    gap: 12px;
    height: 100%;
    min-height: 48px;
}
.brand-name {
    font-weight: 800;
    color: var(--text-primary);
    letter-spacing: -0.02em;
    line-height: 1;
}
.brand-accent {
    background: var(--gradient-hero);
    background-clip: text;
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
}
.nav-rule {
    height: 1px;
    background: linear-gradient(90deg, transparent, var(--border-strong), transparent);
    margin: 6px 0 22px;
}

/* ═══ HOME PAGE — HERO ═══ */
.hero-container {
    text-align: center;
    padding: 80px 20px 60px;
    background:
        radial-gradient(ellipse at top, rgba(99,102,241,0.18), transparent 70%),
        radial-gradient(ellipse at bottom right, rgba(236,72,153,0.10), transparent 60%);
    border: 1px solid var(--border);
    border-radius: 24px;
    margin-bottom: 40px;
    position: relative;
    overflow: hidden;
}
.hero-logo {
    display: flex;
    justify-content: center;
    margin-bottom: 28px;
}
.hero-logo .brand { justify-content: center; }
.cta-banner {
    text-align: center;
    padding: 28px;
    background: var(--gradient-card);
    border: 1px solid rgba(99,102,241,0.3);
    border-radius: var(--radius);
    margin-bottom: 16px;
}
.cta-banner h3 { margin: 0 0 6px 0; color: var(--text-primary); }
.cta-banner p { margin: 0; color: var(--text-secondary); }
.hero-badge {
    display: inline-block;
    padding: 6px 16px;
    background: rgba(99,102,241,0.12);
    border: 1px solid rgba(99,102,241,0.3);
    border-radius: 20px;
    color: #b6c0ff;
    font-size: 0.85em;
    font-weight: 600;
    margin-bottom: 24px;
    letter-spacing: 0.5px;
}
.hero-title {
    font-size: 4em;
    font-weight: 800;
    line-height: 1.1;
    margin: 0 0 24px 0;
    background: var(--gradient-hero);
    background-clip: text;
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    letter-spacing: -0.03em;
}
.hero-subtitle {
    font-size: 1.3em;
    color: var(--text-secondary);
    max-width: 720px;
    margin: 0 auto 32px;
    line-height: 1.6;
}
@media (max-width: 768px) {
    .hero-title { font-size: 2.5em; }
    .hero-subtitle { font-size: 1em; }
}

/* ═══ HOME PAGE — FEATURE CARDS ═══ */
.feature-card {
    background: var(--bg-card);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: 28px 24px;
    height: 100%;
    margin-bottom: 22px;   /* spațiu între rândurile de carduri */
    transition: transform 0.25s ease, border-color 0.25s ease, box-shadow 0.25s ease, background 0.25s ease;
    position: relative;
    overflow: hidden;
}
.feature-card::before {
    content: '';
    position: absolute;
    top: 0; left: 0; right: 0;
    height: 3px;
    background: var(--gradient-hero);
    opacity: 0;
    transition: opacity 0.25s;
}
.feature-card:hover {
    transform: translateY(-4px);
    border-color: rgba(99,102,241,0.5);
    background: var(--bg-card-hover);
    box-shadow: var(--shadow-lg);
}
.feature-card:hover::before { opacity: 1; }
.feature-icon {
    margin-bottom: 16px;
    display: inline-flex;
    width: 56px; height: 56px;
    align-items: center; justify-content: center;
    border-radius: 14px;
    background: var(--gradient-card);
    border: 1px solid var(--border);
    color: #aab6ff;   /* culoarea iconițelor SVG (currentColor) */
}
.feature-icon svg { display: block; }
.feature-title {
    font-size: 1.2em;
    font-weight: 700;
    color: var(--text-primary);
    margin-bottom: 12px;
}
.feature-desc {
    color: var(--text-secondary);
    line-height: 1.6;
    font-size: 0.95em;
}

/* ═══ STATS SECTION ═══ */
.stat-card {
    text-align: center;
    padding: 24px;
    background: var(--gradient-card);
    border: 1px solid var(--border);
    border-radius: var(--radius);
}
.stat-value {
    font-size: 2.5em;
    font-weight: 800;
    background: var(--gradient-hero);
    background-clip: text;
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    line-height: 1;
}
.stat-label {
    margin-top: 8px;
    color: var(--text-muted);
    font-size: 0.85em;
    text-transform: uppercase;
    letter-spacing: 1px;
    font-weight: 600;
}

/* ═══ AUTH FORMS ═══ */
.auth-container {
    max-width: 460px;
    margin: 32px auto 16px;
    padding: 32px 40px;
    background: var(--bg-card);
    border: 1px solid var(--border);
    border-radius: 20px;
    box-shadow: var(--shadow-lg);
}
.auth-title {
    font-size: 2em;
    font-weight: 800;
    background: var(--gradient-hero);
    background-clip: text;
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    margin-bottom: 8px;
    text-align: center;
}
.auth-subtitle {
    text-align: center;
    color: var(--text-muted);
    margin-bottom: 4px;
}
/* formularul (login/register) devine un card continuu sub antet */
[data-testid="stForm"] {
    background: var(--bg-card);
    border: 1px solid var(--border);
    border-radius: var(--radius);
    padding: 24px 26px;
    box-shadow: var(--shadow-md);
}

/* ═══ USER CHIP ═══ */
.user-chip {
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 12px 14px;
    background: var(--gradient-card);
    border: 1px solid var(--border);
    border-radius: 14px;
    margin-bottom: 14px;
}
.user-avatar {
    width: 38px; height: 38px;
    border-radius: 50%;
    background: var(--gradient-hero);
    display: flex;
    align-items: center;
    justify-content: center;
    color: white;
    font-weight: 700;
    font-size: 0.95em;
    box-shadow: var(--shadow-glow);
}
.user-name { font-weight: 600; color: var(--text-primary); line-height: 1.2; }
.user-meta { font-size: 0.78em; color: var(--text-muted); }

/* ═══ SIDEBAR ═══ */
[data-testid="stSidebar"] {
    background: linear-gradient(180deg, #0c1120, #0a0e1a);
    border-right: 1px solid var(--border);
}
[data-testid="stSidebar"] .stButton > button {
    border-radius: var(--radius-sm);
}

/* ═══ CHAT HISTORY SIDEBAR ═══ */
.chat-history-item {
    display: block;
    padding: 10px 12px;
    border-radius: 8px;
    background: transparent;
    border: 1px solid transparent;
    margin-bottom: 4px;
    cursor: pointer;
    transition: all 0.15s;
}
.chat-history-item:hover {
    background: var(--bg-card-hover);
    border-color: var(--border);
}
.chat-history-item.active {
    background: rgba(99,102,241,0.12);
    border-color: var(--primary);
}
.chat-title-text {
    font-weight: 500;
    color: var(--text-primary);
    font-size: 0.9em;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
}
.chat-date-text {
    font-size: 0.72em;
    color: var(--text-muted);
    margin-top: 2px;
}

/* ═══ DOWNLOAD (.docx) — buton vizibil, verde-emerald ═══ */
[data-testid="stDownloadButton"] > button {
    background: linear-gradient(135deg, #10b981, #059669) !important;
    border: none !important;
    color: #fff !important;
    font-weight: 700 !important;
    border-radius: var(--radius-sm) !important;
    box-shadow: 0 6px 20px rgba(16,185,129,0.35) !important;
}
[data-testid="stDownloadButton"] > button:hover {
    transform: translateY(-2px);
    box-shadow: 0 12px 30px rgba(16,185,129,0.5) !important;
}

/* ═══ LINK BUTTON (Google Calendar) — albastru profesional ═══ */
[data-testid="stLinkButton"] a {
    background: linear-gradient(135deg, #3b82f6, #2563eb) !important;
    border: none !important;
    color: #fff !important;
    font-weight: 700 !important;
    border-radius: var(--radius-sm) !important;
    box-shadow: 0 6px 20px rgba(59,130,246,0.35) !important;
}
[data-testid="stLinkButton"] a:hover {
    transform: translateY(-2px);
    box-shadow: 0 12px 30px rgba(59,130,246,0.5) !important;
}

/* ═══ BUTON „OPREȘTE GENERAREA" (roșu plin, lat, sus în bulă — vizibil) ═══ */
.st-key-stop_generation { margin-bottom: 10px; }
.st-key-stop_generation button {
    background: linear-gradient(135deg, var(--danger), #be123c) !important;
    border: none !important;
    color: #fff !important;
    font-weight: 700 !important;
    border-radius: var(--radius-sm) !important;
    box-shadow: 0 6px 20px rgba(244,63,94,0.38) !important;
}
.st-key-stop_generation button:hover {
    background: linear-gradient(135deg, #fb7185, var(--danger)) !important;
    box-shadow: 0 12px 30px rgba(244,63,94,0.55) !important;
    transform: translateY(-2px);
}
/* punct pulsatil care semnalează „în curs de generare" pe butonul de stop */
.st-key-stop_generation button::before {
    content: '';
    display: inline-block;
    width: 8px; height: 8px;
    margin-right: 8px;
    border-radius: 50%;
    background: #fff;
    animation: pulse 1.2s infinite;
    vertical-align: middle;
}

/* ═══ GUEST WARNING ═══ */
.guest-warning {
    background: linear-gradient(135deg, rgba(245,158,11,0.12), rgba(244,63,94,0.08));
    border: 1px solid rgba(245,158,11,0.4);
    border-radius: 12px;
    padding: 14px 18px;
    margin: 12px 0;
    color: #ffc56b;
}

/* ═══ INTRO BOX (chat) ═══ */
.intro-box {
    background: var(--gradient-card);
    border: 1px solid rgba(99,102,241,0.3);
    border-radius: var(--radius);
    padding: 24px 28px;
    margin-bottom: 16px;
}
.intro-box h4 { margin-top: 0; color: #b6c0ff; }
.intro-box code {
    background: rgba(0,0,0,0.3);
    padding: 2px 8px;
    border-radius: 4px;
    color: #fcd34d;
}

/* ═══ ALERTS (st.info / success / warning / error) ═══ */
[data-testid="stAlert"] {
    border-radius: 12px;
    border: 1px solid var(--border);
}

/* ═══ FOOTER ═══ */
.app-footer {
    text-align: center;
    padding: 32px 16px 16px;
    color: var(--text-muted);
    font-size: 0.85em;
    border-top: 1px solid var(--border);
    margin-top: 48px;
}

/* ═══ TABELE (orar / examene) ═══ */
[data-testid="stMarkdownContainer"] table {
    width: 100%;
    border-collapse: separate;
    border-spacing: 0;
    margin: 8px 0 4px;
    border: 1px solid var(--border);
    border-radius: 12px;
    overflow: hidden;
    font-size: 0.9em;
    box-shadow: var(--shadow-sm);
}
[data-testid="stMarkdownContainer"] thead th {
    background: rgba(99,102,241,0.16);
    color: var(--text-primary);
    font-weight: 700;
    text-align: left;
    padding: 9px 13px;
    border-bottom: 1px solid var(--border-strong);
    white-space: nowrap;
}
[data-testid="stMarkdownContainer"] td {
    padding: 8px 13px;
    border-bottom: 1px solid var(--border);
    color: var(--text-secondary);
    vertical-align: top;
}
[data-testid="stMarkdownContainer"] tbody tr:last-child td { border-bottom: none; }
[data-testid="stMarkdownContainer"] tbody tr:nth-child(even) td { background: rgba(255,255,255,0.02); }
[data-testid="stMarkdownContainer"] tbody tr:hover td { background: rgba(99,102,241,0.08); }

/* ═══ TABEL EXAMENE (grid cu buton „Adaugă în Calendar" pe fiecare rând) ═══ */
/* Containerul bordat care înfășoară tabelul de examene */
[data-testid="stChatMessage"] [data-testid="stVerticalBlockBorderWrapper"] {
    border-radius: 12px !important;
    border-color: var(--border) !important;
    background: rgba(255,255,255,0.015);
    box-shadow: var(--shadow-sm);
}
/* Antetul coloanelor */
.exam-th {
    display: block;
    font-size: 0.72em;
    font-weight: 700;
    letter-spacing: 0.04em;
    text-transform: uppercase;
    color: var(--primary-light);
}
/* Celulele de date */
.exam-td {
    display: block;
    font-size: 0.88em;
    line-height: 1.35;
    color: var(--text-secondary);
    word-break: break-word;
}
.exam-td.muted { color: var(--text-muted); font-style: italic; font-size: 0.8em; }
/* Linia subțire dintre rânduri */
hr.exam-rule {
    border: none;
    border-top: 1px solid var(--border);
    margin: 8px 0;
}
/* Butonul „Adaugă" din rând — compact, vertical-centrat lângă datele examenului */
[data-testid="stChatMessage"] [data-testid="stLinkButton"] a {
    padding: 0.32rem 0.5rem !important;
    font-size: 0.8em !important;
    box-shadow: 0 3px 10px rgba(59,130,246,0.30) !important;
}

/* ═══ SCROLLBAR ═══ */
::-webkit-scrollbar { width: 10px; height: 10px; }
::-webkit-scrollbar-track { background: transparent; }
::-webkit-scrollbar-thumb {
    background: var(--border-strong);
    border-radius: 8px;
}
::-webkit-scrollbar-thumb:hover { background: var(--primary); }

/* ═══ HIDE STREAMLIT BRANDING ═══ */
#MainMenu { visibility: hidden; }
footer { visibility: hidden; }
header[data-testid="stHeader"] { background: transparent; }
</style>
"""


def inject_global_css() -> None:
    """Apelată la începutul fiecărei pagini pentru a aplica stilurile."""
    st.markdown(GLOBAL_CSS, unsafe_allow_html=True)


# Alias prietenos (cerut în brief); aceeași funcție, alt nume.
load_custom_css = inject_global_css
