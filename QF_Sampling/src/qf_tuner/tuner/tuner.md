| 相對路徑                            | 內容                       | 誰使用              |
| ------------------------------- | ------------------------ | ---------------- |
| `instruction.md`                | 工作目標、允許修改的範圍、完成條件        | AI agent 讀取      |
| `task.toml`                     | 環境、時間、資源、驗收與成果設定         | Harbor 讀取        |
| `environment/Dockerfile`        | 建立 Python 環境、安裝依賴、放入工作檔案 | Harbor／Docker 使用 |
| `environment/quality_filter.py` | **你現在的 filter 原始版本**     | 複製到工作環境後，由 AI 修改 |
| `environment/requirements.txt`  | filter 需要的套件             | 建立環境時安裝          |
| `environment/data/dev.csv`      | AI 可以查看的開發資料及標籤          | AI 分析與實驗         |
| `environment/evaluate_dev.py`   | 開發階段的快速測試程式              | AI 自己執行          |
| `tests/test.sh`                 | 正式驗收的啟動腳本                | Harbor 執行        |
| `tests/evaluate.py`             | **我們寫的正式評分程式**           | `test.sh` 呼叫     |
| `tests/data/test.csv`           | 正式驗收使用的資料及標籤             | 評分程式使用           |
