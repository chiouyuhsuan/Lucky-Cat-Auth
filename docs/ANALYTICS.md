# GA4 追蹤說明

- 資源：Lucky-Cat-Auth／串流：貓貓抽獎機
- 評估 ID：`G-NT2E29RTNT`（寫在 `js/analytics.js`，四個頁面都會載入）
- 加強型評估（GA4 自動收集）：網頁瀏覽、捲動、外部連結、站內搜尋、影片、檔案下載、表單互動

## 隱私
不送 Email、貓名、照片、選出的號碼。使用者 ID 只送 Firebase 帳號編號（登入後才有）。

## 排除自己的流量
- 在自己的每個瀏覽器（手機、電腦都要）打開一次 `網址?internal=1`，之後這個瀏覽器完全不送資料
- 取消：打開 `網址?internal=0`
- 在 localhost 測試時不送資料

## 檢查事件有沒有送出
打開 `網址?ga_debug=1`，再到 GA4「管理 → DebugView」看即時事件；瀏覽器主控台也會印出 `[GA4]` 紀錄。
註：`internal=1` 的瀏覽器即使加上 `ga_debug=1` 也不會送出。

## 每個事件都會帶的參數
| 參數 | 值 |
|---|---|
| `site_language` | zh／en／ja（網站語言，不是瀏覽器語言） |
| `logged_in` | yes／no／unknown（登入狀態還沒確認時是 unknown） |

## 事件清單

### 選號流程（首頁）
| 事件 | 何時送 | 參數 |
|---|---|---|
| `page_view` | 首頁內換頁（上傳、等待、結果、紀錄、登入） | `page_name`：upload／loading／result／profile／email-auth／home |
| `login_prompt_show` | 未登入按「開始選號」跳出登入提示 | |
| `login_prompt_choice` | 在登入提示做選擇 | `choice`：google／email／skip |
| `select_lottery` | 選樂透 | `lottery_type`：tw／us／jp |
| `photo_upload` | 照片檢查完成 | `result`：pass／not_animal／bad_file；`focus_found`：yes／no；`detected_by`；`file_type`；`file_size_kb`；`photo_shape` |
| `same_cat_choice` | 輸入的貓名已存在時的選擇 | `choice`：same／new |
| `generate_numbers` | 號碼產生 | `lottery_type`；`cat_type`：existing／new；`days_to_draw`（距開獎幾天，僅大樂透） |
| `card_view` | 圖卡顯示（含切換尺寸） | `source`：result／records；`aspect`：9:16／4:5；`card_color`；`lottery_type` |
| `share` | 按分享或下載圖卡 | `method`：shared／downloaded／cancelled；`aspect`；`source`；`card_color` |
| `save_draw` | 選號成功存檔 | `lottery_type`；`cat_type` |
| `new_round` | 按「再選一次」 | `after_save`：yes／no |

### 帳號
| 事件 | 參數 |
|---|---|
| `login` | `method`：google／email |
| `sign_up` | `method`：email |
| `login_error`、`sign_up_error` | `method`；`error_code`（Firebase 錯誤代碼） |
| `password_reset_request` | `result`：ok 或錯誤代碼 |
| `logout` | |

### 紀錄頁
| 事件 | 參數 |
|---|---|
| `mark_purchased` | `action`：on／off |
| `card_view`、`share` | `source`：records |

### 排行榜、貓咪牆、關於
| 事件 | 參數 |
|---|---|
| `rank_tab` | `tab`：prize／rate／latest |
| `map_country_click` | `country_code`；`cats_in_country` |
| `rank_filter_clear` | |
| `wall_filter` | `filter`：all／won／tw／recent |
| `wall_photo_open` | `status`：won／lost／pending／untracked；`lottery_type`；`same_photo_times` |
| `language_change` | `new_language` |
| `internal_link_click` | `link_area`：nav／nav_cta／cta／link；`link_path` |

### 錯誤
| 事件 | 參數 |
|---|---|
| `card_error` | `source` |
| `save_draw_error` | `error_code` |
| `js_error` | `error_message`（前 100 字）；`error_source`（每次開啟頁面最多 5 筆） |

## GA4 後台要手動設定的項目
1. **自訂維度**（管理 → 自訂定義 → 建立自訂維度，範圍選「事件」）：
   `site_language`、`logged_in`、`lottery_type`、`page_name`、`result`、`choice`、`cat_type`、`source`、`aspect`、`card_color`、`method`、`tab`、`filter`、`status`、`action`、`error_code`
   ＋ 範圍選「使用者」：`logged_in`（使用者屬性）
2. **自訂指標**（範圍「事件」）：`days_to_draw`、`file_size_kb`
3. **關鍵事件**（管理 → 事件 → 標為關鍵事件）：`generate_numbers`、`share`、`save_draw`、`sign_up`
4. **資料保留**：管理 → 資料保留 → 改成 14 個月（預設只有 2 個月，探索報表只能看保留期內的資料）
5. **漏斗探索**：探索 → 漏斗探索，步驟依序 `page_view`（page_name = upload）→ `photo_upload`（result = pass）→ `generate_numbers` → `share` 或 `save_draw`
