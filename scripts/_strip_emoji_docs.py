"""One-shot script: strip emoji characters from all Markdown and YAML docs."""
import re
import pathlib

REPLACEMENTS = [
    ('\u2705', '[PASS]'),  # ✅
    ('\u274c', '[FAIL]'),  # ❌
    ('\u26a0\ufe0f', '[WARN]'), ('\u26a0', '[WARN]'),  # ⚠️ ⚠
    ('\U0001f534', '[HIGH]'),  # 🔴
    ('\U0001f7e1', '[MED]'),   # 🟡
    ('\U0001f7e2', '[LOW]'),   # 🟢
    ('\u2139\ufe0f', '[INFO]'), ('\u2139', '[INFO]'),
    ('\U0001f6a8', '[ALERT]'),  # 🚨
    ('\U0001f512', '[SECURE]'),
    ('\U0001f513', '[UNLOCKED]'),
    ('\U0001f6e1\ufe0f', '[SHIELD]'), ('\U0001f6e1', '[SHIELD]'),
    ('\u26a1', '[FAST]'),   # ⚡
    ('\U0001f3af', '[TARGET]'),
    ('\U0001f4cb', '[DOC]'),    # 📋
    ('\U0001f4ca', '[CHART]'),  # 📊
    ('\U0001f4c8', '[TREND]'),  # 📈
    ('\U0001f4c9', '[DOWN]'),   # 📉
    ('\U0001f50d', '[SEARCH]'), # 🔍
    ('\U0001f50e', '[SEARCH]'), # 🔎
    ('\U0001f5c2\ufe0f', '[FILES]'), ('\U0001f5c2', '[FILES]'),
    ('\U0001f4c1', '[DIR]'),
    ('\U0001f4c2', '[DIR]'),
    ('\U0001f4a1', '[NOTE]'),   # 💡
    ('\u2728', '[NEW]'),        # ✨
    ('\U0001f680', '[LAUNCH]'), # 🚀
    ('\U0001f3d7\ufe0f', '[BUILD]'), ('\U0001f3d7', '[BUILD]'),
    ('\U0001f9ea', '[TEST]'),   # 🧪
    ('\U0001f9e0', '[AI]'),     # 🧠
    ('\U0001f517', '[LINK]'),   # 🔗
    ('\U0001f500', '[FLOW]'),   # 🔀
    ('\U0001f310', '[GLOBAL]'), # 🌐
    ('\U0001f4be', '[SAVE]'),   # 💾
    ('\U0001f5a5\ufe0f', '[SYS]'), ('\U0001f5a5', '[SYS]'),
    ('\u2699\ufe0f', '[CONFIG]'), ('\u2699', '[CONFIG]'),
    ('\U0001f527', '[TOOL]'),   # 🔧
    ('\U0001f528', '[BUILD]'),  # 🔨
    ('\U0001f4dd', '[NOTE]'),   # 📝
    ('\U0001f4cc', '[PIN]'),    # 📌
    ('\U0001f3c1', '[DONE]'),   # 🏁
    ('\U0001f389', '[SUCCESS]'),# 🎉
    ('\U0001f4a5', '[CRITICAL]'),# 💥
    ('\U0001f525', '[HOT]'),    # 🔥
    ('\u2753', '[?]'),  # ❓
    ('\u2757', '[!]'),  # ❗
    ('\u203c\ufe0f', '[!!]'), ('\u203c', '[!!]'),
    ('\u2714\ufe0f', '[PASS]'), ('\u2714', '[PASS]'),  # ✔️ ✔
    ('\u2717', '[FAIL]'),  # ✗
    ('\u2718', '[FAIL]'),  # ✘
    ('\u2713', '[PASS]'),  # ✓
    ('\u2716', ''),        # ✖  (heavy X, strip)
    ('\u2746', ''),        # ✦
    ('\U0001f3e6', '[BANK]'),
    ('\U0001f464', '[USER]'),
    ('\U0001f465', '[USERS]'),
    ('\U0001f441\ufe0f', '[VIEW]'), ('\U0001f441', '[VIEW]'),
    ('\U0001f4da', '[DOCS]'),   # 📚
    ('\U0001f4d6', '[GUIDE]'),  # 📖
    ('\U0001f511', '[KEY]'),    # 🔑
    ('\U0001f9e9', '[MODULE]'), # 🧩
    ('\u23f1\ufe0f', '[TIMER]'), ('\u23f1', '[TIMER]'),
    ('\u23f0', '[CLOCK]'),
    ('\U0001f4e1', '[API]'),    # 📡
    ('\U0001f514', '[ALERT]'),  # 🔔
    ('\U0001f4ac', '[MSG]'),    # 💬
    ('\U0001f4e3', '[ANNOUNCE]'),
    ('\U0001f5e3\ufe0f', '[SPEAK]'), ('\U0001f5e3', '[SPEAK]'),
    ('\U0001f6e0\ufe0f', '[TOOLS]'), ('\U0001f6e0', '[TOOLS]'),
    ('\U0001f504', '[SYNC]'),   # 🔄
    ('\u21a9\ufe0f', '[BACK]'), ('\u21a9', '[BACK]'),
]

# Broad residual emoji sweep
LEFTOVER = re.compile(
    r'[\U0001F300-\U0001FBFF'
    r'\U00002600-\U000027BF'
    r'\U0001F004-\U0001F0CF'
    r'\uFE0F]',
    re.UNICODE,
)

ROOT = pathlib.Path(__file__).parent.parent

TARGET_ROOT_MD = [
    'README.md', 'IMPLEMENTATION.md', 'PR_SUMMARY.md',
    'DOCUMENTATION_INDEX.md', 'ARCHITECTURE.md', 'QUICKSTART.md',
    'WIKI_SUMMARY.md', 'WIKI_DEPLOYMENT.md', 'API_REFERENCE.md',
]

files_changed = []


def clean(path: pathlib.Path) -> None:
    text = path.read_text(encoding='utf-8', errors='replace')
    original = text
    for emoji, replacement in REPLACEMENTS:
        text = text.replace(emoji, replacement)
    text = LEFTOVER.sub('', text)
    if text != original:
        path.write_text(text, encoding='utf-8')
        files_changed.append(str(path.relative_to(ROOT)))


for fname in TARGET_ROOT_MD:
    p = ROOT / fname
    if p.exists():
        clean(p)

for md in (ROOT / 'wiki').glob('*.md'):
    clean(md)

for yf in (ROOT / 'prompts').glob('*.yaml'):
    clean(yf)

print(f"Modified {len(files_changed)} files:")
for f in files_changed:
    print(f"  {f}")
