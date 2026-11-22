#!/usr/bin/env python3
"""롱블랙 UT 버전 빌드 도구

구조
  base/longblack_v0.html   공통 기준본(BASE). 다른 세션에서 고친 원본을 그대로 덮어쓴다.
  versions/vN.json         버전마다 고유한 수정(edits/css/js)과 기록(purpose/log).
  registry.json            게시 주소(slug/url) 기록. 게시 후 채운다.
  out/<id>/index.html      결과물. out/<id>/fonts/ 에 폰트.

원칙
  - BASE에는 손대지 않는다. 결과물은 BASE + 표시용 레이어(<!-- UT-LAYER -->) + 버전 수정.
  - 버전 수정의 find 문자열은 BASE 안에 정확히 1번 있어야 한다. 0번/여러 번이면 그 버전은
    빌드하지 않고 멈춘다(공통 수정 때문에 버전 수정이 깨졌다는 신호).
  - 레이어는 표시 블록 사이에만 들어가므로, BASE 게시본에서 블록을 지우면 원본이 그대로 나온다.

사용
  python3 build.py            # BASE + 전체 버전
  python3 build.py v3         # v3만 (다른 버전 파일은 건드리지 않음)
  python3 build.py base v1 v2
  python3 build.py --ingest 새원본.html   # 새 원본을 가명 처리해 base/에 넣기 (원본 실명은 저장 안 함)
  python3 build.py --extract 게시본.html > base/longblack_v0.html   # 게시본에서 BASE 복원

가명
  pseudonym.json 의 name/email 로 LB_DATA.user 를 바꾼다. 실명은 어떤 파일에도 남기지 않는다.
  build 는 기준본의 user 가 가명과 다르면 멈춘다(--ingest 를 거치지 않은 원본 방지).
"""
import hashlib, json, re, sys, shutil, datetime, pathlib

ROOT = pathlib.Path(__file__).resolve().parent
BASE = ROOT / 'base' / 'longblack_v0.html'
VERS = ROOT / 'versions'
OUT = ROOT / 'out'
TARGET = 'artifact'  # main()에서 --pages 면 'pages' (출력 docs/, 폰트는 원본 CDN 사용)
REG = ROOT / 'registry.json'
FONT = ROOT / 'assets' / 'PretendardVariable.woff2'
IDS = ['v1', 'v2', 'v3', 'v4', 'v5']

MARK = {
    'layer': ('<!-- UT-LAYER:START -->', '<!-- UT-LAYER:END -->'),
    'badge': ('<!-- UT-BADGE:START -->', '<!-- UT-BADGE:END -->'),
    'patch': ('<!-- UT-PATCH:START -->', '<!-- UT-PATCH:END -->'),
    'hub': ('<!-- UT-HUB:START -->', '<!-- UT-HUB:END -->'),
}


def esc(s):
    return (str(s).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;').replace('"', '&quot;'))


def block(kind, body):
    a, b = MARK[kind]
    return f'{a}\n{body}\n{b}'


PSEUDO = ROOT / 'pseudonym.json'
USER_RE = re.compile(r'"user":\{"name":"(?P<name>[^"]*)","email":"(?P<email>[^"]*)"')


def pseudonymize(html):
    ps = json.loads(PSEUDO.read_text(encoding='utf-8'))
    html, n = USER_RE.subn(lambda m: '"user":{"name":' + json.dumps(ps['name'], ensure_ascii=False) + ',"email":' + json.dumps(ps['email'], ensure_ascii=False), html)
    if n != 1:
        raise SystemExit(f'가명 처리 실패: user 데이터가 {n}곳 있음 (1곳이어야 함)')
    return html


def check_pseudonym(html):
    ps = json.loads(PSEUDO.read_text(encoding='utf-8'))
    m = USER_RE.search(html)
    if not m or m.group('name') != ps['name'] or m.group('email') != ps['email']:
        raise SystemExit('기준본이 가명 처리되지 않았습니다. python3 build.py --ingest <원본> 으로 넣어 주세요.')


def extract(html):
    """게시본에서 UT 블록을 모두 지워 BASE 원본을 돌려준다."""
    t = re.search(r'<script type="application/json" id="ut-orig-title">(.*?)</script>', html, re.S)
    if t:
        html = re.sub(r'<title>.*?</title>', '<title>' + json.loads(t.group(1)) + '</title>', html, count=1, flags=re.S)
    for a, b in MARK.values():
        html = re.sub(r'\n?' + re.escape(a) + r'.*?' + re.escape(b), '', html, flags=re.S)
    html = re.sub(r"(const KEY = '[^']*?)__ut_[a-z0-9]+(';)", r'\1\2', html)
    return html


def layer(vid, label, extra_css=''):
    font = '' if TARGET == 'pages' else "@font-face{font-family:Pretendard;src:url(fonts/PretendardVariable.woff2) format('woff2-variations'),url(fonts/PretendardVariable.woff2) format('woff2');font-weight:45 920;font-style:normal;font-display:swap}"
    js = (
        "(function(){var V={id:'%s',label:'%s'};window.UT=V;"
        "var m=/^#(?:(v\\d+|base)(-ut)?|(ut))$/i.exec(location.hash||'');if(m&&m[3])m[2]='-ut';var hide=false;"
        "try{if(m&&m[2])sessionStorage.setItem('ut_hide','1');if(m&&!m[2])sessionStorage.removeItem('ut_hide');hide=sessionStorage.getItem('ut_hide')==='1';}catch(e){hide=!!(m&&m[2]);}"
        "V.hide=hide;document.documentElement.setAttribute('data-utv',V.id);if(hide)document.documentElement.setAttribute('data-ut-hide','1');"
        "if(m){try{history.replaceState(null,'',location.pathname+location.search+'#/');}catch(e){}if(location.hash!=='#/')location.hash='#/';}"
        "})();"
    ) % (vid, label)
    css = font + (
        ".proto-badge{display:none!important}"
        "#utBadge{position:fixed;left:8px;bottom:8px;z-index:300;padding:3px 8px;border-radius:4px;background:rgba(0,0,0,.6);color:#fff;font:500 10px/1.4 Pretendard,sans-serif;letter-spacing:.3px;pointer-events:none}"
        "#utBadge b{font-weight:700}"
        "[data-ut-hide] #utBadge .v{display:none}"
    )
    return block('layer', f'<script>{js}</script>\n<style>{css}{extra_css}</style>')


def badge(label):
    return block('badge', f'<div id="utBadge"><span class="v"><b>{esc(label)}</b> · </span>프로토타입 · 공식 서비스 아님</div>')


def apply_edits(html, edits, vid):
    for i, e in enumerate(edits, 1):
        n = html.count(e['find'])
        if n != 1:
            raise SystemExit(f'[{vid}] 수정 {i}번 적용 실패: 기준본에서 찾을 문자열이 {n}번 나옴 → {e["find"][:60]!r}')
        html = html.replace(e['find'], e['replace'])
    return html


def inject(html, head_add, body_add):
    i = html.find('<head>')
    if i < 0:
        raise SystemExit('기준본에 <head>가 없습니다')
    j = html.find('<meta charset="utf-8">', i)
    pos = (j + len('<meta charset="utf-8">')) if j >= 0 else i + len('<head>')
    html = html[:pos] + '\n' + head_add + html[pos:]
    k = html.rfind('</body>')
    return html[:k] + body_add + '\n' + html[k:]


def set_title(html, title):
    return re.sub(r'<title>.*?</title>', f'<title>{esc(title)}</title>', html, count=1, flags=re.S)


def write(vid, html):
    if TARGET == 'pages':
        d = OUT if vid == 'base' else OUT / vid
        d.mkdir(parents=True, exist_ok=True)
        (d / 'index.html').write_text(html, encoding='utf-8')
        return
    d = OUT / vid
    (d / 'fonts').mkdir(parents=True, exist_ok=True)
    (d / 'index.html').write_text(html, encoding='utf-8')
    shutil.copyfile(FONT, d / 'fonts' / 'PretendardVariable.woff2')


def build_version(base, base_sha, vid):
    v = json.loads((VERS / f'{vid}.json').read_text(encoding='utf-8'))
    label = 'UT-' + v['label']
    html = apply_edits(base, v.get('edits', []), vid)
    html, k = re.subn(r"const KEY = '([^']+)';", lambda m: f"const KEY = '{m.group(1)}__ut_{vid}';", html, count=1)
    if not k:
        print(f'[{vid}] 경고: 저장 키(const KEY)를 찾지 못해 저장 공간을 나누지 못함')
    html = set_title(html, f'{label} · 롱블랙 프로토타입')
    meta = {'id': vid, 'label': v['label'], 'base_sha': base_sha, 'built': now(), 'purpose': v.get('purpose', ''),
            'log': v.get('log', []), 'edits': v.get('edits', []), 'css': v.get('css', ''), 'js': v.get('js', '')}
    patch_json = json.dumps(meta, ensure_ascii=False, indent=1).replace('</', '<\\/')
    body = badge(label) + '\n' + block('patch', f'<script type="application/json" id="ut-patch">{patch_json}</script>' + (f'\n<script>{v["js"]}</script>' if v.get('js') else ''))
    html = inject(html, layer(vid, label, v.get('css', '')), body)
    write(vid, html)
    return meta


def hub_panel(base_sha, metas):
    reg = json.loads(REG.read_text(encoding='utf-8')) if REG.exists() else {}
    rows = ''
    for m in metas:
        if TARGET == 'pages':
            u = f'{m["id"]}/'
            link = f'<a href="{u}">/{m["id"]}/</a> · <a href="{u}#ut">/{m["id"]}/#ut</a>'
        else:
            url = reg.get(m['id'], {}).get('url', '')
            link = (f'<a href="{esc(url)}#{m["id"]}">#{m["id"]}</a> · <a href="{esc(url)}#{m["id"]}-ut">#{m["id"]}-ut</a>') if url else '<i>게시 전</i>'
        same = '같음' if m['base_sha'] == base_sha else f'<b style="color:#ff5126">이전 기준({m["base_sha"][:7]})</b>'
        logs = ''.join(f'<li><span>{esc(l.get("date",""))}</span> {esc(l.get("what",""))}</li>' for l in m.get('log', [])[-3:])
        rows += (f'<tr><th>{esc(m["label"])}</th><td>{link}<div class="pp">{esc(m.get("purpose",""))}</div><ul>{logs}</ul></td>'
                 f'<td>{len(m.get("edits", []))}개{" +CSS" if m.get("css") else ""}{" +JS" if m.get("js") else ""}</td><td>{same}</td></tr>')
    css = ("#utHubBtn{position:fixed;right:12px;bottom:12px;z-index:400;height:40px;padding:0 14px;border-radius:999px;background:#191919;color:#fff;font:600 13px/40px Pretendard,sans-serif;box-shadow:0 2px 10px rgba(0,0,0,.3)}"
           "#utHub{position:fixed;inset:0;z-index:401;display:none;background:rgba(0,0,0,.5);overflow:auto;padding:24px 12px}#utHub.show{display:block}"
           "#utHub .p{max-width:400px;margin:0 auto;background:#fff;border-radius:10px;padding:20px 16px;font:14px/1.5 Pretendard,sans-serif;color:#191919}"
           "#utHub h4{font-size:17px;font-weight:700}#utHub .s{margin-top:4px;color:#666;font-size:12px}"
           "#utHub table{width:100%;margin-top:14px;border-collapse:collapse}#utHub th,#utHub td{padding:10px 4px;border-top:1px solid #e7e7e7;vertical-align:top;text-align:left;font-size:12px}"
           "#utHub th{width:30px;font-size:14px}#utHub a{color:#5962ff;text-decoration:underline}#utHub .pp{margin-top:4px;color:#444}"
           "#utHub ul{margin-top:4px;padding-left:0;list-style:none;color:#666}#utHub li span{color:#999}"
           "#utHub .how{margin-top:14px;padding:12px;border-radius:8px;background:#f5f5f5;font-size:12px;line-height:1.6;color:#444}"
           "#utHub .x{float:right;font-size:20px;line-height:1}")
    html = (f'<style>{css}</style><button id="utHubBtn" type="button">UT 버전 관리</button>'
            f'<div id="utHub"><div class="p"><button class="x" type="button" data-close>×</button><h4>공통 반영 페이지 (BASE)</h4>'
            f'<p class="s">이 화면이 V1~V5의 공통 기준본입니다. 기준 {base_sha[:7]} · 빌드 {now()}</p>'
            f'<table><tr><th></th><td><b>주소</b> (뒤에 #ut 를 붙이면 참가자용: 버전 표시 숨김)</td><td><b>고유 수정</b></td><td><b>기준본</b></td></tr>{rows}</table>'
            '<div class="how"><b>공통 수정</b>: 이 BASE를 고친 뒤 Claude에게 "BASE를 V1~V5에 반영해줘"(또는 일부 버전만). '
            '각 버전의 고유 수정은 유지됩니다. 고유 수정이 새 기준본과 부딪히면 그 버전만 멈추고 알려 드립니다.<br>'
            '<b>버전 하나만 수정</b>: "V3만 ○○ 바꿔줘" → V3 주소만 다시 게시됩니다.</div></div></div>'
            "<script>(function(){var b=document.getElementById('utHubBtn'),h=document.getElementById('utHub');"
            "b.onclick=function(){h.classList.add('show')};h.onclick=function(e){if(e.target===h||e.target.hasAttribute('data-close'))h.classList.remove('show')};})();</script>")
    return block('hub', html)


def now():
    return datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=9))).strftime('%Y-%m-%d %H:%M')


def main(argv):
    global TARGET, OUT
    if '--pages' in argv:
        argv = [a for a in argv if a != '--pages']
        TARGET, OUT = 'pages', ROOT / 'docs'
    if argv[:1] == ['--extract']:
        sys.stdout.write(extract(pathlib.Path(argv[1]).read_text(encoding='utf-8')))
        return
    if argv[:1] == ['--ingest']:
        raw = pathlib.Path(argv[1]).read_text(encoding='utf-8')
        raw = extract(raw) if '<!-- UT-' in raw else raw
        BASE.write_text(pseudonymize(raw), encoding='utf-8')
        print('기준본 교체 완료(가명 처리):', BASE)
        return
    base = BASE.read_text(encoding='utf-8')
    check_pseudonym(base)
    if '<!-- UT-' in base:
        raise SystemExit('기준본에 UT 블록이 섞여 있습니다. --extract로 원본을 먼저 복원하세요.')
    base_sha = hashlib.sha1(base.encode('utf-8')).hexdigest()
    targets = argv or ['base'] + IDS
    for vid in [t for t in targets if t in IDS]:
        m = build_version(base, base_sha, vid)
        print(f'{vid}: 빌드 완료 (고유 수정 {len(m["edits"])}개, 기준 {base_sha[:7]})')
    if 'base' in targets:
        metas = []
        for vid in IDS:
            p = OUT / vid / 'index.html'
            if p.exists():
                mm = re.search(r'<script type="application/json" id="ut-patch">(.*?)</script>', p.read_text(encoding='utf-8'), re.S)
                metas.append(json.loads(mm.group(1).replace('<\\/', '</')))
        ot = re.search(r'<title>(.*?)</title>', base, re.S)
        keep = block('patch', '<script type="application/json" id="ut-orig-title">' + json.dumps(ot.group(1) if ot else '', ensure_ascii=False) + '</script>')
        html = set_title(base, 'UT-BASE · 공통 반영 페이지')
        html = inject(html, layer('base', 'UT-BASE'), badge('UT-BASE') + '\n' + keep + '\n' + hub_panel(base_sha, metas))
        write('base', html)
        print(f'base: 빌드 완료 (버전 {len(metas)}개 표시)')


if __name__ == '__main__':
    main(sys.argv[1:])
