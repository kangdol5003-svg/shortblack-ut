"""UT 빌드 결과를 헤드리스 크롬으로 열어 확인 (file:// 로 열기, 서버 없음)."""
import asyncio, pathlib
from playwright.async_api import async_playwright

OUT = pathlib.Path(__file__).resolve().parent / 'out'
CASES = [('v1', '#v1'), ('v3', '#v3-ut'), ('base', '#base')]


async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch(executable_path='/usr/bin/google-chrome')
        errs = []
        for vid, h in CASES:
            ctx = await b.new_context(viewport={'width': 400, 'height': 766})
            pg = await ctx.new_page()
            pg.on('pageerror', lambda e, v=vid: errs.append(f'{v}: {e}'))
            await pg.goto((OUT / vid / 'index.html').as_uri() + h)
            await pg.wait_for_timeout(1500)
            info = await pg.evaluate("""()=>({hash:location.hash,title:document.title,
                badge:document.getElementById('utBadge')?.innerText,
                home:!!document.querySelector('.hero'),
                font:document.fonts.check('16px Pretendard')})""")
            print(vid, h, info)
            await pg.screenshot(path=f'/tmp/shot_{vid}.png')
            await pg.click('.hero')
            await pg.wait_for_timeout(600)
            print('  TODAY 클릭 후:', await pg.evaluate("()=>[location.hash, !!document.querySelector('#article')]"))
            if vid == 'base':
                await pg.goto((OUT / vid / 'index.html').as_uri() + h)
                await pg.wait_for_timeout(800)
                await pg.click('#utHubBtn')
                await pg.wait_for_timeout(300)
                await pg.screenshot(path='/tmp/shot_hub.png')
            await ctx.close()
        print('페이지 오류:', errs or '없음')
        await b.close()

if __import__("sys").argv[1:] != ["names"]:
    asyncio.run(main())


async def check_names():
    async with async_playwright() as p:
        b = await p.chromium.launch(executable_path='/usr/bin/google-chrome')
        pg = await (await b.new_context(viewport={'width': 400, 'height': 766})).new_page()
        await pg.goto((OUT / 'v2' / 'index.html').as_uri() + '#v2')
        await pg.wait_for_timeout(1000)
        await pg.click('[data-act="drawer"]'); await pg.wait_for_timeout(400)
        print('드로어:', (await pg.inner_text('.drawer .acct')).replace('\n', ' / '))
        await pg.screenshot(path='/tmp/shot_drawer.png')
        await pg.evaluate("location.hash='#/history'"); await pg.wait_for_timeout(600)
        print('마이페이지:', (await pg.inner_text('.my .prof')).replace('\n', ' / ')[:80])
        await b.close()

if __name__ == '__main__' and __import__('sys').argv[1:] == ['names']:
    asyncio.run(check_names())
