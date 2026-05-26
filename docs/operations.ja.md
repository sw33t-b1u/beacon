# BEACON 運用ガイド

## MISP キャッシュの更新

### 目的

BEACON は [MISP Galaxy](https://github.com/MISP/misp-galaxy) の
脅威アクタークラスター（`cache/misp-threat-actor.json`）のローカルコピーを、
アクターの帰属・標的業界の分類・巧妙さスコアリングのタクソノミーフォールバックとして使用する。
このキャッシュは `MispClient` によって読み込まれ、PIR 生成中に照会される（Initiative D/E）。

キャッシュを最新の状態に保つことで、MISP コミュニティから新たに追加された
アクターや更新されたメタデータが、コード変更なしに BEACON の出力に反映される。

### 更新の実行

```bash
# デフォルト: cache/misp-threat-actor.json に書き込む
uv run python -m cmd.refresh_misp_cache

# カスタム出力パスを指定
uv run python -m cmd.refresh_misp_cache --output /path/to/misp-threat-actor.json

# ディスクに書き込まずにダウンロードを検証
uv run python -m cmd.refresh_misp_cache --dry-run

# すべてのオプション
uv run python -m cmd.refresh_misp_cache --help
```

### 推奨 cron エントリ（毎日 03:00 ローカル時間）

```cron
0 3 * * * cd /path/to/beacon && unset ALL_PROXY all_proxy HTTP_PROXY http_proxy HTTPS_PROXY https_proxy FTP_PROXY ftp_proxy RSYNC_PROXY GRPC_PROXY grpc_proxy NO_PROXY no_proxy; export UV_CACHE_DIR=$TMPDIR/uv-cache; uv run python -m cmd.refresh_misp_cache >> /var/log/beacon/misp_refresh.log 2>&1
```

cron エントリを有効化する前にログディレクトリを作成すること:

```bash
mkdir -p /var/log/beacon
```

### 失敗時のセマンティクス

本スクリプトは**フェイルセーフ**な設計となっている:

- ダウンロードまたはパースが失敗した場合、**既存のキャッシュはそのまま残る**
  （`tempfile` + `os.replace` によるアトミック書き込みにより、部分的な書き込みは発生しない）。
- 下流の BEACON パイプラインは古いキャッシュを使い続け、失敗せずに
  構造化 `warning` ログ行を出力する。
- 終了コード: `0` = 成功、`1` = HTTP/ネットワークエラー、`2` = JSON パースエラー。

### アラートガイダンス

繰り返しの失敗を検知するために `/var/log/beacon/misp_refresh.log` を監視すること。
推奨チェック:

1. **連続失敗（3 回以上）:** 3 日以上連続して `"event": "misp_cache_refresh.fetch_failed"`
   または `"misp_cache_refresh.http_error"` を検索する。

2. **キャッシュの鮮度:** キャッシュファイルの `_metadata.last_auto_sync` を確認する:

   ```bash
   python3 -c "import json; d=json.load(open('cache/misp-threat-actor.json')); \
       print(d.get('_metadata', {}).get('last_auto_sync', 'N/A'))"
   ```

   タイムスタンプが 7 日以上前の場合はアラートを発する。

3. **ログ形式:** すべての行は構造化 JSON（`structlog` 経由）。成功行の例:

   ```json
   {"event": "misp_cache_refresh.done", "output_path": "cache/misp-threat-actor.json",
    "last_auto_sync": "2026-05-23T03:00:01Z", "values_count": 994, "timestamp": "..."}
   ```
