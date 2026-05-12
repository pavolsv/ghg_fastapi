# 待解決事項

## P0 — 安全性問題

### 1. 密碼明文儲存與 log 外洩

- **位置**: `routers/login.py:48-67`, `routers/register.py:28-50`
- **問題**: 登入時用 `print(username)`、`print(password)`、`print(VerificationCode)` 將敏感資訊輸出到 stdout/log；密碼以明文儲存於資料庫（沒有 hash）。
- **影響**: 生產環境下，任何有權限看 log 的人都能取得使用者密碼。
- **建議**: 移除所有 `print()` 敏感資料的語句；改用 `passlib` 或 `bcrypt` 對密碼做 hash 後再儲存與比對。

### 2. Session 密鑰硬編碼

- **位置**: `main.py:36`
- **問題**: `SessionMiddleware(secret_key="1shh3345sknn1h1b244xf")` 的密鑰直接寫死在原始碼中。
- **影響**: 所有開發者共用同一組密鑰，若任一環境外洩，可偽造 session 竊取登入狀態。
- **建議**: 從環境變數讀取（如 `os.getenv("SESSION_SECRET_KEY")`），並在正式環境使用獨立隨機值。

---

## P1 — 資料庫連線不一致

### 3. 多重 engine / session 來源

- **位置**:
  - `database.py:17` — 有環境變數邏輯
  - `dependencies.py:4-5` — 寫死 `sqlite:///./database.db`
  - `routers/login.py:52-53` — 寫死 `sqlite:///database.db`
  - `routers/register.py:30-31` — 寫死 `sqlite:///database.db`
  - `routers/set.py:16-17` — 寫死 `sqlite:///database.db`
  - 其他 router 內也有自建 `engine`
- **問題**: 同時存在多個 `create_engine()` 實體且路徑不統一（`./database.db` vs `database.db`），加上 `dependencies.py` 不認 `DATABASE_FILE` 環境變數，可能導致寫入不同檔案、資料彼此讀不到。
- **影響**: 登入認證寫到 A DB，主程式功能讀 B DB，資料不一致或完全找不到。
- **建議**: 只保留 `database.py` 的 engine，所有 router 統一從 `database` 或 `dependencies` 匯入 `get_session()`，不再各自建立 engine。

---

## P2 — 邏輯錯誤

### 4. 密碼唯一性檢查

- **位置**: `routers/register.py:33-45`
- **問題**: 註冊時對 `email`、`account`、`password` 三欄位都做唯一性檢查，若任一個重複就拒絕註冊。
- **影響**: 不同使用者無法設定相同密碼，完全不合理；且錯誤訊息會洩漏「此密碼已有人使用」，暴露資料庫狀態。
- **建議**: 移除密碼的查重邏輯，只保留 `account` 與 `email` 的唯一性檢查。

### 5. `model.py` 中 `Account.password` 沒有約束

- **位置**: `model.py:24`
- **問題**: `password: str` 只是一般字串欄位，沒有最小長度或複雜度驗證。
- **建議**: 搭配 hash 方案，在註冊 API 中做最小長度（如 8 碼）檢查。

---

## P3 — 測試覆蓋不足

### 6. 測試僅涵蓋根路徑

- **位置**: `tests/test_health.py`
- **問題**: 只有一個測試，驗證 `GET /` 回傳 200 與 text/html。完全沒有測試登入、註冊、DB 操作、權限控管、Alembic migration 或 OCR 流程。
- **影響**: 重構時沒有回歸保護，很容易改壞而不自知。
- **建議**: 至少補上登入/註冊流程測試、session 權限阻擋測試、以及關鍵 router 的基本回應測試。

---

## P3+ — 程式碼品質

### 7. `alembic/env.py` 未納入 CI 一致性檢查

- 目前 CI 已被移除，但若未來重新啟用，應確保 `alembic upgrade head` 在測試前執行，且 migration 檔案與 `model.py` 保持一致。

### 8. 無 `.env` 載入機制

- `env.template.txt` 僅為說明檔，應用程式啟動時不會自動載入。
- 建議使用 `python-dotenv` 在 `main.py` 啟動時載入 `.env` 檔案。
