"""使用 Playwright 將 HTML 轉換為 PDF。"""

from pathlib import Path

from playwright.async_api import async_playwright


async def html_to_pdf(
    html_content: str,
    output_path: str | Path,
    page_size: str = "A4",
    margin: dict | None = None,
) -> Path:
    """將 HTML 字串渲染為 PDF 檔案。"""
    margin = margin or {
        "top": "2cm",
        "bottom": "2cm",
        "left": "2cm",
        "right": "2cm",
    }
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page()
        await page.set_content(html_content, wait_until="networkidle")
        await page.pdf(
            path=str(output_path),
            format=page_size,
            margin=margin,
            print_background=True,
        )
        await browser.close()

    return output_path
