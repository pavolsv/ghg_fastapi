from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, HttpUrl, conint
import httpx
from bs4 import BeautifulSoup
import pandas as pd

router = APIRouter(prefix="/get_water", tags=["get_water"])
templates = Jinja2Templates(directory="templates")


ConstrainedDepth = conint(ge=1, le=2)

class CrawlRequest(BaseModel):
    url: HttpUrl
    depth: ConstrainedDepth = 1 # type: ignore
    timeout: int = 10


@router.post("/get_page")
async def crawl(req: CrawlRequest):
    """
    Fetch a single page (or depth=2: fetch links on that page) and return basic data.
    Returns: url, status_code, title, text_snippet, links
    """
    async def fetch(url: str):
        try:
            async with httpx.AsyncClient(timeout=req.timeout, follow_redirects=True, verify=False) as client:
                r = await client.get(url)
                return r
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"request failed: {e}")

    resp = await fetch(str(req.url))
    if resp.status_code != 200:
        raise HTTPException(status_code=resp.status_code, detail="Failed to fetch page")

    soup = BeautifulSoup(resp.text, "html.parser")
    main_page_contents = []
    for div in soup.find_all("div", class_="main_page_content"):
        main_page_contents.append(div.get_text(strip=True))
        print("\n")

    return {"main_page_content": main_page_contents}


@router.get("/", response_class=HTMLResponse)
async def show_water(request: Request):
    # Fetch real data from crawling
    try:
        async with httpx.AsyncClient(timeout=10, follow_redirects=True, verify=False) as client:
            resp = await client.get("https://www.water.gov.tw/dist5/Subject/Detail/2269?nodeId=6562")
        soup = BeautifulSoup(resp.text, "html.parser")
        
        # Extract tables
        table_data = []
        for table in soup.find_all("table"):
            columns = table.find_all("tr")
            for column in columns:
                rows = column.find_all("td")
                if rows:
                    row_data = [row.get_text(strip=True) for row in rows]
                    table_data.append(row_data)
                    print(row_data)  # Print each row
        
        # Convert to DataFrame for HTML display
        if table_data:
            # Dynamically determine column count from first row
            num_cols = len(table_data[0]) if table_data else 3
            df = pd.DataFrame(table_data)
            html_table = df.to_html(classes="table table-striped", index=False, header=False)
        else:
            html_table = "<p>No tables found.</p>"
    except Exception as e:
        print(f"Error: {e}")
        html_table = f"<p>Error: {e}</p>"

    return templates.TemplateResponse(
        "get_water.html",
        {"request": request, "html_table": html_table}
    )
