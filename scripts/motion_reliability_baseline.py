"""Read-only saved-project screenshots; no AI jobs or renders are submitted."""
import argparse
import json
from pathlib import Path
from urllib.request import urlopen

from playwright.sync_api import expect, sync_playwright


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project', default='09782d1f7c63')
    parser.add_argument('--base', default='http://127.0.0.1:4319')
    parser.add_argument('--output', default='test-results/reliability/baseline')
    args = parser.parse_args()
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    with urlopen(f'{args.base}/api/jobs/{args.project}') as response:
        job = json.load(response)
    assert job['status'] == 'complete', job['status']
    report = {'project': args.project, 'errors': [], 'requests_blocked': [], 'views': []}
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel='chrome', headless=True)
        try:
            page = browser.new_page(viewport={'width': 1440, 'height': 1000})
            page.on('pageerror', lambda error: report['errors'].append(str(error)))

            def read_only(route):
                if route.request.method not in ('GET', 'HEAD', 'OPTIONS'):
                    report['requests_blocked'].append(route.request.url)
                    route.fulfill(status=409, json={'detail': 'Read-only screenshot inspection.'})
                else:
                    route.continue_()

            page.route('**/api/**', read_only)
            page.goto(f'{args.base}/?project={args.project}', wait_until='networkidle')
            expect(page.locator('#finished')).to_be_visible()
            for view in ('result', 'compare'):
                page.locator(f'#{view}-tab').click()
                page.wait_for_function('document.getElementById("result-video").readyState >= 2')
                page.evaluate('''async () => {
                    await Promise.all(['source-video','result-video'].map(id => new Promise(resolve => {
                        const video = document.getElementById(id);
                        video.pause(); video.muted = true;
                        if (!Number.isFinite(video.duration)) return resolve();
                        const seconds = Math.min(2.5, video.duration / 2);
                        if (Math.abs(video.currentTime-seconds) < 0.001) return resolve();
                        video.addEventListener('seeked', resolve, {once: true});
                        video.currentTime = seconds;
                        setTimeout(resolve, 3000);
                    })));
                }''')
                for width in (1440, 390):
                    page.set_viewport_size({'width': width, 'height': 1000})
                    page.wait_for_timeout(200)
                    report['views'].append({
                        'view': view, 'width': width,
                        'scroll_width': page.evaluate('document.documentElement.scrollWidth'),
                        'download_text': page.locator('#download').inner_text(),
                        'download_visible': page.locator('#download').is_visible(),
                        'download_href': page.locator('#download').get_attribute('href'),
                        'summary': page.locator('#finished-summary').inner_text(),
                    })
                    page.screenshot(path=str(output / f'{view}-{width}.png'), full_page=True)
            report['video_states'] = page.evaluate('''() => ['source-video','result-video'].map(id => {
                const video=document.getElementById(id);
                return {id, readyState:video.readyState, duration:video.duration, time:video.currentTime,
                    error:video.error?.message || null, videoWidth:video.videoWidth, videoHeight:video.videoHeight};
            })''')
        finally:
            browser.close()
    (output / 'report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps(report, indent=2))
    assert not report['errors'], report['errors']
    assert not report['requests_blocked'], report['requests_blocked']
    assert all(view['scroll_width'] <= view['width'] for view in report['views']), report['views']


if __name__ == '__main__':
    main()
