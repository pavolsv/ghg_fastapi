"""報告書資料彙整與草稿生成服務。"""

from datetime import datetime
from typing import Any

from jinja2 import Template
from sqlmodel import Session, select

from constants.refrigerant_factors import get_name_by_code
from database import engine
from model import CompanyInfo, Device, EmissionFactor604, EmissionRecord, GWPReference, Report, ReportChapter, ReportSubChapter
from services.llm_writer import generate_chapter

CHAPTER_TITLES: dict[int, str] = {
    1: "公司簡介與政策聲明",
    2: "盤查邊界設定",
    3: "報告溫室氣體排放量",
    4: "數據品質管理",
    5: "基準年",
    6: "參考文獻",
}

DEFAULT_SUB_CHAPTERS: dict[int, list[str]] = {
    1: ["1.1 公司簡介", "1.2 政策聲明"],
    2: ["2.1 組織邊界設定", "2.2 營運邊界"],
    3: ["3.1 排放源鑑別", "3.2 排放量彙總", "3.3 排放趨勢分析"],
    4: ["4.1 量化方法", "4.2 有效位數", "4.3 不確定性評估"],
    5: ["5.1 基準年選定", "5.2 基準年排放量"],
    6: ["6.1 參考文獻"],
}

# 所有章節採用變數填空模板，由後端預設產生，使用者可於編輯頁覆寫
_DEFAULT_CHAPTER_TEMPLATES: dict[int, str] = {
    1: """
<div class="report-chapter">
    
    <h3>1.1 前言與政策背景</h3>
    <p>自 1997 年 12 月《京都議定書》簽署，至 2015 年《巴黎協定》通過，全球先進國家與氣候組織均加速研擬因應溫室氣體減量之具體措施。我國響應聯合國氣候變遷目標，於西元 2023 年（民國 112 年）1 月三讀通過《氣候變遷因應法》，明確將「2050 淨零排放」目標入法，並由環境部氣候變遷署依法公告應盤查登錄溫室氣體排放量之事業主體。</p>
    <p><strong>{{ company.company_name }}</strong>（以下簡稱本公司）為因應全球永續發展趨勢、善盡企業社會責任（CSR/ESG），並對接國際碳邊境調整機制（如 CBAM 等供應鏈碳要求），特引進本網頁版溫室氣體碳盤查系統。透過系統化、結構化的數據管理流程，全面進行組織邊界與營運邊界之溫室氣體盤查，確實掌控公司內部碳排放現況，進而訂定改善策略與自主減量計畫，共同朝低碳轉型邁進。</p>

    <h3>1.2 報告書預期用途</h3>
    <p>本報告書及其附屬溫室氣體盤查清冊，其預期用途包含但不限於：</p>
    <ul>
        <li>作為對接國際綠色供應鏈、滿足客戶碳足跡與低碳產品採購要求之佐證資料。</li>
        <li>作為金管會「上市櫃公司永續發展路徑圖」或國家發展委員會、經濟部產業發展署低碳化轉型補助之依據。</li>
        <li>作為本公司執行 ISO 14064-1:2018 外部第三方查證（如合理保證等級）之基準文件。</li>
        <li>提供本公司決策階層作為擬定年度節能減碳目標、綠電採購及溫室氣體減量方案之依據。</li>
    </ul>

    <h3>1.3 公司基本資料</h3>
    <p>本公司之基本營運據點與組織主體資訊如下：</p>
    <table class="report-table" style="width:100%; border-collapse: collapse; margin: 15px 0;" border="1">
        <tr style="background-color: #fafafa;">
            <th style="padding: 10px; width: 30%; text-align: left;">基本資訊欄位</th>
            <th style="padding: 10px; text-align: left;">主體登記內容</th>
        </tr>
        <tr>
            <td style="padding: 10px; font-weight: bold;">公司名稱</td>
            <td style="padding: 10px;">{{ company.company_name }}</td>
        </tr>
        <tr>
            <td style="padding: 10px; font-weight: bold;">統一編號</td>
            <td style="padding: 10px; font-family: monospace;">{{ company.tax_id }}</td>
        </tr>
        <tr>
            <td style="padding: 10px; font-weight: bold;">公司地址 / 廠區地理邊界</td>
            <td style="padding: 10px;">{{ company.address }}</td>
        </tr>
        <tr>
            <td style="padding: 10px; font-weight: bold;">公司負責人</td>
            <td style="padding: 10px;">{{ company.owner }}</td>
        </tr>
        <tr>
            <td style="padding: 10px; font-weight: bold;">盤查專案聯絡人</td>
            <td style="padding: 10px;">{{ company.contact_person }}</td>
        </tr>
        <tr>
            <td style="padding: 10px; font-weight: bold;">聯絡電話</td>
            <td style="padding: 10px; font-family: monospace;">{{ company.telephone }}</td>
        </tr>
        <tr>
            <td style="padding: 10px; font-weight: bold;">電子郵件信箱</td>
            <td style="padding: 10px; font-family: monospace;">{{ company.email }}</td>
        </tr>
    </table>
</div>
""",

    2: """
<div class="report-chapter">
    <p>溫室氣體盤查之邊界設定，分為「組織邊界（Organizational Boundary）」與「營運邊界（Operational Boundary）」，旨在明確界定本公司之法律與實質營運控制範圍，確保盤查清冊之完整性與無重複認列。</p>

    <h3>2.1 組織邊界設定方法</h3>
    <p>依據 ISO 14064-1:2018 國際標準之指引，組織邊界之界定可採取以下兩種判定基準：</p>
    <ul>
        <li><strong>營運控制權法（Operational Control Approach）：</strong> 組織對於其所管理或實質控制營運之所有據點與設施，其溫室氣體排放量由該組織 100% 全額認列。</li>
        <li><strong>股權持分法（Equity Share Approach）：</strong> 依其在個別設施中所持有的股權或實質資產持分比例，按比例折算並認列溫室氣體排放量。</li>
    </ul>
    <p>經本公司內部永續推動委員會評估，本次溫室氣體盤查之組織邊界，係採用：<strong>{{ report.org_boundary_method }}</strong>。</p>
    <p>本公司對於組織邊界內所有實質擁有營運控制權之行政區域、辦公室、生產車間及公共設施，皆進行 100% 之排放量認列。具體地理範圍侷限於：<strong>{{ company.address }}</strong> 邊界內之主體結構。</p>

    <h3>2.2 營運邊界與排放源鑑別分類</h3>
    <p>本公司依據營運控制權之範疇，全面鑑別營運邊界內之溫室氣體源別。依據 ISO 標準，溫室氣體種類全面涵蓋：二氧化碳(CO₂)、甲烷(CH₄)、氧化亞氮(N₂O)、氫氟碳化物(HFCs)、全氟碳化物(PFCs)、六氟化硫(SF₆)及三氟化氮(NF₃)七大主流氣體。</p>
    <p>經本盤查系統全面核對與現場設備盤點，本公司邊界內共鑑別出 <strong>{{ emission.source_count }}</strong> 個溫室氣體排放源，涵蓋 <strong>{{ emission.device_count }}</strong> 部用能設備。營運邊界分類說明如下：</p>
    
    <div style="background-color: #f9f9f9; padding: 12px; border-left: 4px solid #3498db; margin: 15px 0;">
        <strong>系統營運邊界備註：</strong><br>
        {{ report.operational_boundary_note or "本公司盤查範疇主要涵蓋直接溫室氣體排放（範疇一/類別1），包含固定燃燒源、移動燃燒源、冷氣與化糞池之逸散排放源等；以及能源間接溫室氣體排放（範疇二/類別2），主要為外購自台灣電力公司之電能耗用。" }}
    </div>

</div>
""",

    3: """
<div class="report-chapter">
    <p>本章節呈現本公司於盤查年度內之溫室氣體排放總量統計，所有計算結果均已由系統之碳計算引擎換算為二氧化碳當量（公噸 CO₂e/年）。</p>

    <h3>3.1 溫室氣體總排放量彙整</h3>
    <p>經由系統對各排放源活動數據之精確量化，<strong>{{ company.company_name }}</strong> 於西元 <strong>{{ report.inventory_year }}</strong> 盤查年度內，溫室氣體總排放量（不含生質燃料碳排放）共計 <strong>{{ emission.total_co2e }}</strong> 公噸 CO₂e。</p>
    <p>其中，直接溫室氣體排放（範疇一）為 <strong>{{ emission.scope1_total }}</strong> 公噸 CO₂e，佔總排放量比例為 <strong>{{ emission.scope1_percentage }}%</strong>；間接能源溫室氣體排放（範疇二）為 <strong>{{ emission.scope2_total }}</strong> 公噸 CO₂e，佔總排放量比例為 <strong>{{ emission.scope2_percentage }}%</strong>。詳細總量彙整結果如下表所示：</p>

    <table class="report-table" style="width:100%; border-collapse: collapse; margin-top: 15px;" border="1">
        <thead>
            <tr style="background-color: #2c3e50; color: #ffffff; font-weight: bold;">
                <th style="padding: 10px; text-align: center;">盤查範疇別項目</th>
                <th style="padding: 10px; text-align: center;">排放型式分類</th>
                <th style="padding: 10px; text-align: right;">排放量 (公噸 CO₂e/年)</th>
                <th style="padding: 10px; text-align: right;">佔總排放比例 (%)</th>
            </tr>
        </thead>
        <tbody>
            <tr>
                <td rowspan="3" style="text-align: center; font-weight: bold; vertical-align: middle; padding: 10px;">
                    範疇一 (Scope 1)<br>直接排放
                </td>
                <td style="padding: 10px;">1.1 固定燃燒源（發電機、鍋爐等）</td>
                <td style="text-align: right; padding: 10px; font-family: monospace;">{{ emission.combustion_total }}</td>
                <td style="text-align: right; padding: 10px; font-family: monospace;">{{ emission.combustion_percentage }}%</td>
            </tr>
            <tr>
                <td style="padding: 10px;">1.2 移動燃燒源（公司公務車輛等）</td>
                <td style="text-align: right; padding: 10px; font-family: monospace;">{{ emission.mobile_total }}</td>
                <td style="text-align: right; padding: 10px; font-family: monospace;">{{ emission.mobile_percentage }}%</td>
            </tr>
            <tr>
                <td style="padding: 10px;">1.4 逸散排放源（冷氣、化糞池、滅火器）</td>
                <td style="text-align: right; padding: 10px; font-family: monospace;">{{ emission.refrigerant_total }}</td>
                <td style="text-align: right; padding: 10px; font-family: monospace;">{{ emission.refrigerant_percentage }}%</td>
            </tr>
            <tr style="background-color: #fafafa;">
                <td style="text-align: center; font-weight: bold; padding: 10px;">範疇一小計</td>
                <td style="padding: 10px; font-weight: bold; color: #555;">範疇一直接碳排放合計</td>
                <td style="text-align: right; padding: 10px; font-weight: bold; font-family: monospace;">{{ emission.scope1_total }}</td>
                <td style="text-align: right; padding: 10px; font-weight: bold; font-family: monospace;">{{ emission.scope1_percentage }}%</td>
            </tr>
            <tr>
                <td style="text-align: center; font-weight: bold; vertical-align: middle; padding: 10px;">
                    範疇二 (Scope 2)<br>能源間接排放
                </td>
                <td style="padding: 10px;">2.1 輸入能源間接排放（外購台電電力）</td>
                <td style="text-align: right; padding: 10px; font-family: monospace;">{{ emission.electricity_total }}</td>
                <td style="text-align: right; padding: 10px; font-family: monospace;">{{ emission.electricity_percentage }}%</td>
            </tr>
            <tr style="background-color: #fafafa;">
                <td style="text-align: center; font-weight: bold; padding: 10px;">範疇二小計</td>
                <td style="padding: 10px; font-weight: bold; color: #555;">範疇二電力間接碳排放合計</td>
                <td style="text-align: right; padding: 10px; font-weight: bold; font-family: monospace;">{{ emission.scope2_total }}</td>
                <td style="text-align: right; padding: 10px; font-weight: bold; font-family: monospace;">{{ emission.scope2_percentage }}%</td>
            </tr>
            <tr style="background-color: #eaf2ff; font-weight: bold;">
                <td colspan="2" style="padding: 10px; text-align: center;">本公司年度排放總量 (Total Emissions)</td>
                <td style="text-align: right; padding: 10px; color: #d9534f; font-family: monospace;">{{ emission.total_co2e }}</td>
                <td style="text-align: right; padding: 10px; font-family: monospace;">100.00%</td>
            </tr>
        </tbody>
    </table>
    
    <h3>3.2 數據比例與減碳優先度分析</h3>
    <p>根據盤查數據結果，本公司溫室氣體排放之佔比分析如下：</p>
    <ul>
        <li><strong>間接能耗（範疇二）佔比分析：</strong> 本公司外購電力排放量佔總碳排放 <strong>{{ emission.scope2_percentage }}%</strong>。由於本公司屬低碳製造/行政辦公據點，外購電力無謎為溫室氣體排放最主要來源。因此，未來公司應將「冷氣溫控排程」、「改採一級能效節能空調」、「照明燈具全面汰換為 LED」列為首要減量方案，以降低不必要之用電負荷。</li>
        <li><strong>直接排放（範疇一）佔比分析：</strong> 直接排放總計佔 <strong>{{ emission.scope1_percentage }}%</strong>，其組成主要分布於
            {% if emission.mobile_total|float > emission.refrigerant_total|float %}
                移動源車輛燃油。後續應逐步規劃公務車汰換為油電混合車或純電動車之時程。
            {% else %}
                冷氣空調冷媒逸散與化糞池廢水降解。應加強廠內冷氣管線點檢，減少冷媒維修填充頻率，以控制直接逸散碳排。
            {% endif %}
        </li>
    </ul>
</div>
""",

    4: """
<div class="report-chapter">
    <p>為確保盤查結果具備高度之「可稽核性（Auditability）」與「數據透明度（Transparency）」，本系統遵照環境部公告之運算作業規範，進行計量與不確定性評估。</p>

    <h3>4.1 量化方法學與通用公式</h3>
    <p>本系統所採用之溫室氣體排放量量化技術，全面採取符合 ISO 國際指引之<strong>「排放係數法（Emission Factor Approach）」</strong>或<strong>「質量平衡法（Mass Balance Approach）」</strong>。核心計量公式如下：</p>
    <div style="text-align: center; margin: 15px 0; font-family: monospace; background: #f9f9f9; padding: 12px; border: 1px solid #ddd; border-radius: 4px; font-weight: bold;">
        溫室氣體排放當量 (t CO₂e/年) = 活動數據 &times; 排放係數 &times; GWP 值
    </div>
    <p>其中：</p>
    <ul>
        <li><strong>活動數據（Activity Data）：</strong> 係指企業運營活動中可計量之能耗或物料消耗值，如電力（度）、汽柴油（公升）、天然氣（立方公尺）等。數據均由台電帳單、中油發票或維修憑證等外部第三方單據予以佐證。</li>
        <li><strong>排放係數（Emission Factor）：</strong> 優先引用國家環境部氣候變遷署公告最新版「溫室氣體排放係數管理表（如 6.0.4/7.1.1 版本）」之國家預設值，確保在地合規性。</li>
        <li><strong>全球暖化潛勢值（GWP）：</strong> 採用 <strong>IPCC 第五次（AR5）</strong>評估報告公告之溫室氣體 GWP 換算因子，將非 CO₂ 氣體統一轉換為二氧化碳當量（CO₂e）。</li>
    </ul>

    <h3>4.2 精確度與有效位數管制規範</h3>
    <p>為避免計算過程中因四捨五入造成之累積計量誤差，本盤查數據完全遵循國家登錄平台第四版之有效位數基準：</p>
    <ol>
        <li><strong>活動數據：</strong> 依據慣用單位，輸入系統之活動數據小數位數取至<strong>小數點後第 4 位</strong>，第 5 位四捨五入。</li>
        <li><strong>排放係數：</strong> 引用環境部公告之計算係數，小數位數至多取至<strong>小數點後第 10 位</strong>，第 11 位四捨五入。</li>
        <li><strong>單一排放源排放量：</strong> 活動數據與排放係數相乘後之各氣體排放量，取至<strong>小數點後第 4 位</strong>。</li>
        <li><strong>全廠總排放當量：</strong> 全廠七大溫室氣體排放總量彙整時，四捨五入至<strong>小數點後第 3 位</strong>（以公噸 CO₂e 為單位）。</li>
    </ol>
</div>
""",

    5: """
<div class="report-chapter">
    
    <h3>5.1 基準年選定</h3>
    <p>為有效評估本公司溫室氣體排放量之長期變化趨勢，並追蹤減量成效，本次盤查設定以西元 <strong>{{ report.base_year }}</strong> 年做為溫室氣體排放之基準年度（Base Year）。</p>
    <p>盤查年度 <strong>{{ report.inventory_year }}</strong> 年之所有溫室氣體排放數據，將與基準年 <strong>{{ report.base_year }}</strong> 年之排放數據進行比較分析，以鑑別排放增減趨勢及減量績效。</p>

    <h3>5.2 基準年排放量</h3>
    <p>本公司基準年度（{{ report.base_year }} 年）之溫室氣體排放總量為 <strong>{{ emission.total_co2e }}</strong> 公噸 CO₂e。若基準年之排放量數據經未來重新計算（如因排放係數版本更新、組織邊界調整或計算方法改變），本公司將依 ISO 14064-1:2018 之規定進行基準年重置（Base Year Recalculation），並於後續版本之盤查報告書中揭露變更說明。</p>
</div>
""",

    6: """
<div class="report-chapter">
    <ul>
        <li>溫室氣體排放係數管理表 6.0.4 版</li>
        <li>行政院環境部氣候變遷署「溫室氣體排放量盤查作業指引 2022.5」</li>
        <li>經濟部能源署電力排碳係數</li>
        <li>IPCC Guidelines for National Greenhouse Gas Inventories, 2006</li>
        <li>ISO 14064-1:2018</li>
    </ul>
</div>
""",
}


def _collect_company_data(session: Session, account_id: int | None = None) -> dict[str, Any]:
    """收集單一公司基本資料（優先使用資料較完整的公司）。"""
    stmt = select(CompanyInfo)
    if account_id is not None:
        stmt = stmt.where(CompanyInfo.account_id == account_id)
    companies = session.exec(stmt).all()
    if not companies:
        return {}

    def _completeness(c: CompanyInfo) -> int:
        score = 0
        if c.company_name and len(c.company_name.strip()) > 3:
            score += 3
        if c.address and c.address.strip():
            score += 2
        if c.owner and c.owner.strip():
            score += 1
        return score

    company = max(companies, key=_completeness)
    return {
        "company_name": company.company_name or "",
        "tax_id": company.tax_id or "",
        "address": company.address or "",
        "owner": company.owner or "",
        "contact_person": company.contact_person or "",
        "telephone": company.telephone or "",
        "email": company.email or "",
    }


def _collect_emission_data(
    session: Session,
    year: int,
    account_id: int | None = None,
) -> dict[str, Any]:
    """收集排放數據（與 result 頁面邏輯一致）。"""
    device_stmt = select(Device)
    if account_id is not None:
        device_stmt = device_stmt.where(Device.account_id == account_id)
    devices = session.exec(device_stmt).all()
    device_map = {d.id: d for d in devices}
    device_ids = [d.id for d in devices if d.id is not None]

    if account_id is not None:
        records = (
            session.exec(
                select(EmissionRecord).where(EmissionRecord.device_id.in_(device_ids))
            ).all()
            if device_ids
            else []
        )
    else:
        records = session.exec(select(EmissionRecord)).all()

    emission_type_to_scope = {
        "固定燃燒": "scope1",
        "移動燃燒": "scope1",
        "逸散排放": "scope1",
        "能源間接排放": "scope2",
    }

    total_co2e = 0.0
    scope1_total = 0.0
    scope2_total = 0.0
    by_type: dict[str, float] = {}
    sources = []
    source_count = 0

    for record in records:
        device = device_map.get(record.device_id)
        co2e = float(record.total_co2e or 0.0)
        total_co2e += co2e
        source_count += 1

        emission_type = (device.emission_type if device else "未分類") or "未分類"
        scope = emission_type_to_scope.get(emission_type, "scope1")
        if scope == "scope2":
            scope2_total += co2e
        else:
            scope1_total += co2e

        by_type[emission_type] = by_type.get(emission_type, 0.0) + co2e

        sources.append(
            {
                "name": device.name if device else f"設備#{record.device_id}",
                "emission_type": device.emission_type if device else "未分類",
                "scope": "範疇一" if scope == "scope1" else "範疇二",
                "activity_data": record.activity_data,
                "unit": record.unit or (device.unit if device else ""),
                "co2e": round(co2e, 4),
            }
        )

    scope1_pct = round(scope1_total / total_co2e * 100, 1) if total_co2e else 0
    scope2_pct = round(scope2_total / total_co2e * 100, 1) if total_co2e else 0

    return {
        "total_co2e": round(total_co2e, 4),
        "scope1_total": round(scope1_total, 4),
        "scope2_total": round(scope2_total, 4),
        "scope1_percentage": scope1_pct,
        "scope2_percentage": scope2_pct,
        "source_count": source_count,
        "device_count": len(devices),
        "by_type": {k: round(v, 4) for k, v in by_type.items()},
        "combustion_total": round(by_type.get("固定燃燒", 0), 4),
        "mobile_total": round(by_type.get("移動燃燒", 0), 4),
        "refrigerant_total": round(by_type.get("逸散排放", 0), 4),
        "electricity_total": round(by_type.get("能源間接排放", 0), 4),
        "combustion_percentage": round(by_type.get("固定燃燒", 0) / total_co2e * 100, 1) if total_co2e else 0,
        "mobile_percentage": round(by_type.get("移動燃燒", 0) / total_co2e * 100, 1) if total_co2e else 0,
        "refrigerant_percentage": round(by_type.get("逸散排放", 0) / total_co2e * 100, 1) if total_co2e else 0,
        "electricity_percentage": round(by_type.get("能源間接排放", 0) / total_co2e * 100, 1) if total_co2e else 0,
        "sources": sources,
    }


GAS_FORMAT_MAP = {
    "CO2": "CO₂",
    "CH4": "CH₄",
    "N2O": "N₂O",
    "CO2e": "CO₂e",
    "NF3": "NF₃",
    "SF6": "SF₆",
    "HFC": "HFCₛ",
    "PFC": "PFCₛ",
    "NH3": "NH₃",
}


def _format_gas_type(gas_type_str: str) -> str:
    """格式化氣體種類字串（CO2→CO₂、逗號→頓號）。"""
    if not gas_type_str:
        return ""
    parts = [GAS_FORMAT_MAP.get(p.strip(), p.strip()) for p in gas_type_str.replace("、", ",").split(",")]
    return "、".join(p for p in parts if p)


def _classify_refrigerant_gas(session: Session, refrigerant_code: str) -> str:
    """查詢冷媒對應的溫室氣體族群（HFCₛ / PFCₛ / SF₆ / NF₃）。"""
    if not refrigerant_code:
        return ""
    code = refrigerant_code.strip()
    gwp = session.exec(
        select(GWPReference).where(
            (GWPReference.formula == code)
            | (GWPReference.gas_name_zh == code)
            | (GWPReference.gas_name_en == code)
        )
    ).first()
    if gwp:
        f = (gwp.formula or "").upper()
        if "HFC" in f:
            return "HFCₛ"
        if "PFC" in f:
            return "PFCₛ"
        if f == "SF₆" or "SF6" in f:
            return "SF₆"
        if f == "NF₃" or "NF3" in f:
            return "NF₃"
        if "CFC" in f or "HCFC" in f:
            return "其他"
    return "HFCₛ"


def _build_operational_boundary_table(
    session: Session,
    year: int,
    account_id: int | None = None,
) -> list[dict[str, str]]:
    """建立 2.2 營運邊界彙總表資料。"""
    device_stmt = select(Device)
    if account_id is not None:
        device_stmt = device_stmt.where(Device.account_id == account_id)
    devices = session.exec(device_stmt).all()

    # 預載排放係數以加速查詢
    factors = session.exec(select(EmissionFactor604)).all()
    factor_map: dict[str, dict[str, EmissionFactor604]] = {}
    for f in factors:
        factor_map.setdefault(f.original_code, {})[f.emission_type] = f

    rows: list[dict[str, str]] = []

    SUB_CATEGORY_MAP = {
        "固定燃燒": "固定",
        "移動燃燒": "移動",
        "逸散排放": "逸散",
        "能源間接排放": "外購電力",
    }

    for device in devices:
        emission_type = device.emission_type or ""
        if emission_type == "能源間接排放":
            category = "間接排放"
        else:
            scope = device.scope or "scope1"
            category = "直接排放" if scope == "scope1" else "間接排放"
        sub_category = SUB_CATEGORY_MAP.get(emission_type, emission_type)

        # --- 對應活動（設施種類）---
        activity = device.name or ""
        if emission_type == "逸散排放":
            eq_name = get_name_by_code(device.equipment_category or "")
            if eq_name:
                activity = device.name or eq_name
            rc = device.refrigerant_code
            if rc:
                activity = f"{activity}（{rc}）"
        elif emission_type in ("固定燃燒", "移動燃燒"):
            fuel_name = None
            if device.factor_ref_code:
                factor = factor_map.get(device.factor_ref_code, {}).get(emission_type)
                if factor:
                    fuel_name = factor.name
            if fuel_name:
                wrap = device.name or ""
                activity = f"{wrap}（{fuel_name}）" if wrap else fuel_name
            else:
                activity = device.name or "未命名設備"
        elif emission_type == "能源間接排放":
            activity = "外購電力"
        else:
            activity = device.name or "未命名設備"

        # --- 溫室氣體種類 ---
        if device.gas_type and device.gas_type.strip():
            gas_types = _format_gas_type(device.gas_type)
        elif emission_type in ("固定燃燒", "移動燃燒"):
            fc = device.factor_ref_code
            if fc and fc in factor_map and emission_type in factor_map[fc]:
                gas_types = _format_gas_type(factor_map[fc][emission_type].gas_type)
            else:
                gas_types = "CO₂、CH₄、N₂O"
        elif emission_type == "逸散排放":
            gas_types = _classify_refrigerant_gas(session, device.refrigerant_code or "")
        elif emission_type == "能源間接排放":
            gas_types = "CO₂"
        else:
            gas_types = ""

        rows.append({
            "category": category,
            "sub_category": sub_category,
            "activity": activity,
            "gas_types": gas_types,
            "is_biomass": "否",
        })

    return rows


def build_report_context(report: Report, account_id: int | None = None) -> dict[str, Any]:
    """建構報告書模板所需的資料上下文。"""
    with Session(engine) as session:
        company = _collect_company_data(session, account_id=account_id)
        emission = _collect_emission_data(
            session,
            report.inventory_year,
            account_id=account_id,
        )
        boundary_table = _build_operational_boundary_table(
            session,
            report.inventory_year,
            account_id=account_id,
        )

        return {
            "report": {
                "inventory_year": report.inventory_year,
                "base_year": report.base_year,
                "org_boundary_method": report.org_boundary_method,
                "operational_boundary_note": report.operational_boundary_note or "",
                "status": report.status,
            },
            "company": company,
            "emission": emission,
            "operational_boundary_table": boundary_table,
            "generated_at": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
        }


def build_standalone_report_context(
    inventory_year: int,
    base_year: int | None = None,
    org_boundary_method: str = "控制權法",
    operational_boundary_note: str | None = None,
    account_id: int | None = None,
) -> dict[str, Any]:
    """建立不落資料庫的報告渲染內容，供結果頁直接下載 PDF 使用。"""
    report = Report(
        inventory_year=inventory_year,
        base_year=base_year or inventory_year,
        org_boundary_method=org_boundary_method,
        operational_boundary_note=operational_boundary_note,
    )
    context = build_report_context(report, account_id=account_id)
    context["chapter_titles"] = CHAPTER_TITLES
    context["chapter_contents"] = {}

    for chapter_no in range(1, 7):
        template = Template(_DEFAULT_CHAPTER_TEMPLATES[chapter_no])
        context["chapter_contents"][chapter_no] = template.render(context)

    return context


def _build_llm_data(chapter_no: int, context: dict[str, Any]) -> dict[str, Any]:
    """為特定章節準備要傳給 LLM 的資料。"""
    if chapter_no == 1:
        return context["company"]
    if chapter_no == 3:
        return context["emission"]
    if chapter_no == 5:
        return {
            "base_year": context["report"]["base_year"],
            "inventory_year": context["report"]["inventory_year"],
            "total_co2e": context["emission"]["total_co2e"],
        }
    return {}


async def create_report_draft(
    inventory_year: int,
    base_year: int | None = None,
    org_boundary_method: str = "控制權法",
    operational_boundary_note: str | None = None,
) -> Report:
    """建立報告書草稿，並為指定章節呼叫 LLM 生成敘述文字。"""
    report = Report(
        inventory_year=inventory_year,
        base_year=base_year or inventory_year,
        org_boundary_method=org_boundary_method,
        operational_boundary_note=operational_boundary_note,
    )

    with Session(engine) as session:
        session.add(report)
        session.commit()
        session.refresh(report)

        # 建立 6 個空章節
        for no, title in CHAPTER_TITLES.items():
            chapter = ReportChapter(
                report_id=report.id,
                chapter_no=no,
                title=title,
            )
            session.add(chapter)
        session.commit()

        # 建立預設小節
        for chapter_no, titles in DEFAULT_SUB_CHAPTERS.items():
            for sub_no, title in enumerate(titles, start=1):
                sub = ReportSubChapter(
                    report_id=report.id,
                    chapter_no=chapter_no,
                    sub_no=sub_no,
                    title=title,
                )
                session.add(sub)
        session.commit()

        # 先建構上下文
        context = build_report_context(report)

        # 所有章節使用變數填空模板
        for chapter_no in range(1, 7):
            chapter = session.exec(
                select(ReportChapter).where(
                    ReportChapter.report_id == report.id,
                    ReportChapter.chapter_no == chapter_no,
                )
            ).first()
            if not chapter:
                continue
            template = Template(_DEFAULT_CHAPTER_TEMPLATES[chapter_no])
            rendered = template.render(context)
            chapter.generated_content = rendered
            chapter.edited_content = rendered
            chapter.is_generated_by_llm = False
            session.add(chapter)

        session.commit()
        session.refresh(report)

    return report


def get_chapter_content(report_id: int, chapter_no: int) -> str | None:
    """取得最終要使用的章節內容（edited_content 優先）。"""
    with Session(engine) as session:
        chapter = session.exec(
            select(ReportChapter).where(
                ReportChapter.report_id == report_id,
                ReportChapter.chapter_no == chapter_no,
            )
        ).first()
        if not chapter:
            return None
        return chapter.edited_content or chapter.generated_content or ""
