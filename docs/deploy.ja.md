# BEACON — Cloud Run デプロイガイド

英語版（正本）: [`docs/deploy.md`](deploy.md)

デプロイ前に [docs/setup.ja.md](setup.ja.md) の手順を完了すること。デプロイ前に `make check` がパスすることを確認すること。

---

## クロスリポジトリのデプロイ順序

BEACON・SAGE・TRACE はデプロイ時に循環依存を形成する: BEACON は
`SAGE_API_URL`（sage-api の URL）を必要とし、SAGE の ETL は BEACON が生成する
検証済み `pir.json` を必要とする。この順序で循環を解く — 未解決の依存は後から
`--update-env-vars` で配線するため、BEACON はまだ存在しない `sage-api` の URL を
待ってブロックすることはない。この順序は [SAGE deploy.ja.md](../../sage/docs/deploy.ja.md)
と一致しており、両リポジトリで矛盾しない。

1. **SAGE — まず `sage-api` をデプロイ**（その GCS バケットも）。API は DB が
   無くても起動するため、BEACON が必要とする前に URL が存在する。
2. **BEACON — `beacon-web` をデプロイ。** ステップ 1 の sage-api URL を
   `SAGE_API_URL` に配線し、SAGE 側で BEACON のサービスアカウント（`beacon-sa`）に
   `sage-api` の `roles/run.invoker` を付与する（[SAGE 連携](#sage-連携クロスリポジトリ)参照）。
3. **BEACON — PIR/assets を生成。** ビジネスコンテキストから `pir_output.json` と
   asset 成果物を生成する。
4. **TRACE — validate。** assets・PIR・STIX バンドルを TRACE（すべての SAGE 入力に
   対する単一の検証ゲート）に通す。コマンドは [TRACE リポジトリ](https://github.com/sw33t-b1u/trace)
   を参照（ここでは重複させない）。
5. **SAGE — 配置して ETL 実行。** 検証済み成果物を GCS に配置し `sage-etl` を実行する。

BEACON のデプロイ時に `sage-api` が未デプロイの場合は、`SAGE_API_URL` なしで
`beacon-web` をデプロイし、後から `--update-env-vars` で追加する（[`SAGE_API_URL`（任意）](#day-1-初回デプロイ)
および Day-N 再デプロイ参照）。

---

## Day-0 前提条件

### API の有効化

```sh
source .env
export REGION=${VERTEX_LOCATION:-us-central1}

gcloud services enable \
  run.googleapis.com \
  artifactregistry.googleapis.com \
  cloudbuild.googleapis.com \
  aiplatform.googleapis.com \
  --project=${GCP_PROJECT_ID}
```

### Artifact Registry リポジトリの作成

```sh
gcloud artifacts repositories create cloud-run \
  --repository-format=docker \
  --location=${REGION} \
  --project=${GCP_PROJECT_ID}
```

### サービスアカウントの作成と IAM ロールの付与

デプロイコマンドでサービスアカウントを参照する前に、`beacon-sa` サービスアカウントを作成して必要なロールを付与しておく。

```sh
gcloud iam service-accounts create beacon-sa \
  --display-name="BEACON Web Service" \
  --project=${GCP_PROJECT_ID}

for ROLE in roles/aiplatform.user roles/storage.objectAdmin roles/run.invoker; do
  gcloud projects add-iam-policy-binding ${GCP_PROJECT_ID} \
    --member="serviceAccount:beacon-sa@${GCP_PROJECT_ID}.iam.gserviceaccount.com" \
    --role="${ROLE}"
done
```

> **IAM ロール説明:**
> - `roles/aiplatform.user` — LLM 分析用 Vertex AI Gemini アクセス
> - `roles/storage.objectAdmin` — GCS 成果物（BEACON_STORAGE_BUCKET）の読み書き
> - `roles/run.invoker` — BEACON が OIDC 経由で SAGE Analysis API（`sage-api`）を呼び出すために必要

### GCS バケットの作成（未作成の場合）

```sh
# ストレージバックエンドバケット（BEACON_STORAGE=gcs の場合のみ）
gcloud storage buckets create gs://${BEACON_STORAGE_BUCKET} \
  --location=${REGION} \
  --project=${GCP_PROJECT_ID}
```

---

## Day-1 初回デプロイ

### beacon-web（Cloud Run Service）

```sh
source .env
export REGION=${VERTEX_LOCATION:-us-central1}

# （任意）sage-api がすでにデプロイされている場合は URL を取得
export SAGE_API_URL=$(gcloud run services describe sage-api \
  --region=${REGION} --format='value(status.url)' --project=${GCP_PROJECT_ID} 2>/dev/null || echo "")

export IMAGE=${REGION}-docker.pkg.dev/${GCP_PROJECT_ID}/cloud-run/beacon-web

# Cloud Build でコンテナイメージをビルドしてプッシュ
gcloud builds submit --tag ${IMAGE} --project=${GCP_PROJECT_ID}

# Cloud Run Service としてデプロイ
gcloud run deploy beacon-web \
  --image=${IMAGE} \
  --region=${REGION} \
  --no-allow-unauthenticated \
  --port=8000 \
  --service-account="beacon-sa@${GCP_PROJECT_ID}.iam.gserviceaccount.com" \
  --set-env-vars="GCP_PROJECT_ID=${GCP_PROJECT_ID},VERTEX_LOCATION=${REGION},BEACON_STORAGE=gcs,BEACON_STORAGE_BUCKET=${BEACON_STORAGE_BUCKET},BEACON_STORAGE_PREFIX=${BEACON_STORAGE_PREFIX:-prod/}${SAGE_API_URL:+,SAGE_API_URL=${SAGE_API_URL}}" \
  --project=${GCP_PROJECT_ID}
```

> **`--set-env-vars` vs `--update-env-vars`:** 初回デプロイでは `--set-env-vars` を使って env-var セット全体を一括設定する。以降の変更は `--update-env-vars` を使うこと（Day-N 参照）。既存サービスに `--set-env-vars` を使うと **env-var セット全体が置き換わり**、再指定しなかったキーが無音で削除される。

> **`SAGE_API_URL`（任意）:** BEACON の初回デプロイ時に `sage-api` がまだデプロイされていない場合は、後から `--update-env-vars` で追加する（後述の Day-N 再デプロイを参照）。これは[クロスリポジトリのデプロイ順序](#クロスリポジトリのデプロイ順序)の「後から配線する」分岐である — 可能なら先に `sage-api` をデプロイし、できない場合は後から `SAGE_API_URL` を配線する。

---

## Day-N 再デプロイ

### コード変更のみの場合

env-var の追加・削除がなく、コンテナイメージのみ変更する場合はこのフローを使う。

```sh
export IMAGE=${REGION}-docker.pkg.dev/${GCP_PROJECT_ID}/cloud-run/beacon-web

# 新しいイメージをビルドしてプッシュ
gcloud builds submit --tag ${IMAGE} --project=${GCP_PROJECT_ID}

# Cloud Run Service を更新
gcloud run services update beacon-web \
  --image=${IMAGE} \
  --region=${REGION} \
  --project=${GCP_PROJECT_ID}
```

### 既存リビジョンの env-var 変更

`--update-env-vars` と `--remove-env-vars` を使うこと — **`--set-env-vars` は使わない**。`--set-env-vars` は env-var セット全体を置き換えるため、再指定しなかったキーが無音で削除される。

```sh
# 他の変数に影響せず 1 つの変数を追加・更新する
gcloud run services update beacon-web \
  --update-env-vars=NEW_VAR=value \
  --region=${REGION} \
  --project=${GCP_PROJECT_ID}

# 古い変数を削除しながら新しい変数を追加する
gcloud run services update beacon-web \
  --update-env-vars=NEW_VAR=value \
  --remove-env-vars=OLD_VAR \
  --region=${REGION} \
  --project=${GCP_PROJECT_ID}

# sage-api デプロイ後に SAGE_API_URL を追加する
gcloud run services update beacon-web \
  --update-env-vars="SAGE_API_URL=$(gcloud run services describe sage-api --region=${REGION} --format='value(status.url)' --project=${GCP_PROJECT_ID})" \
  --region=${REGION} \
  --project=${GCP_PROJECT_ID}
```

> **確認:** `gcloud run services describe beacon-web --region=${REGION} --format="value(spec.template.spec.containers[0].env[].name)" --project=${GCP_PROJECT_ID}`

---

## BEACON の運用（アナリストワークフロー）

上記の Day-0/1/N セクションはインフラを立ち上げる手順である。本セクションでは、
GCS バックエンドの BEACON デプロイを使って CTI アナリストが実際に *何をするか*、
どの順序で行うかを説明する。まず **概要** を読んでパイプライン全体を把握すること。
末尾の **詳細コマンド** ブロックは同じ手順を実コマンドでなぞる。

### 概要 — 何ができるか

このフローをたどると、新しいビジネスコンテキスト文書を、クエリ可能な攻撃経路まで
一気通貫で到達させられる。各ステップには存在理由がある:

- **ビジネスコンテキストの作成** — 組織（業種・地理・クラウンジュエル・規制要件）を
  `input/context.md` に記述する。これがすべての下流スコアを駆動する唯一の入力であり、
  これが無ければ BEACON は優先順位付けの基準を持たない。
- **PIR + assets の生成** — そのコンテキストを Priority Intelligence Requirements と
  3 つの asset ドラフト（`assets` / `identity_assets` / `user_accounts`）に変換する。
  散文を、SAGE と TRACE が消費する構造化・スコア済みの成果物へ変える。
- **成果物の GCS への永続化** — ストレージバックエンドが `gcs` の場合、生成・保存される
  すべての成果物はローカルの `output/` ではなく設定されたバケット/プレフィックスに格納
  される。これにより（永続的なローカルディスクを持たない）Cloud Run リビジョンが
  リクエスト間およびパイプラインの他コンポーネントと状態を共有できる。
- **Web ダッシュボードでの閲覧・編集** — ダッシュボードを開き、LLM が知り得ない
  組織既知のフィールド（asset の owner、セキュリティコントロール、CVE マッピング、
  identity/account フラグ）を補完してから再保存する。グラフへ到達する前の
  human-in-the-loop ゲートである。
- **TRACE による検証** — すべての SAGE 入力は単一の検証ゲートである TRACE を通過する。
  これによりスキーマ・参照整合性のエラー（taxonomy の欠落、asset タグの不一致、有効期間
  切れ）がグラフを汚染する前に捕捉される。
- **SAGE によるグラフ取込** — SAGE は検証済み assets をロードし STIX ETL を実行する。
  PIR タグで脅威アクターをフィルタし `pir_adjusted_criticality` を計算する。外部 CTI と
  内部コンテキストがついに合流する場所である。
- **攻撃経路のクエリ** — グラフが投入されたら、SAGE（Analysis API・visualizer・
  ダッシュボードの **Threats** タブ）にアクターカバレッジ・TTP・最もリスクの高い asset を
  クエリする。これが対価であり、Red/Blue/IR チーム向けの優先順位付き攻撃経路インサイトが
  得られる。

この概要だけでアナリストは何が可能かを把握できる — コンテキスト作成、スコア済み成果物の
生成、GCS への永続化、ブラウザでの精緻化、検証、取込、そして最後のクエリ — コマンドを
一切読まずに。

### ストレージバックエンドの選択（GCS と local）

成果物がどこに永続化されるかはストレージバックエンドで決まり、2 つのソースから
次の優先順位で解決される:

**`defaults < .beacon_settings.json（Settings UI）< 環境変数`** — 環境変数が常に勝つ。

- **環境変数** — Cloud Run リビジョンに `BEACON_STORAGE=gcs`・
  `BEACON_STORAGE_BUCKET=<bucket>`・`BEACON_STORAGE_PREFIX=<prefix>` を設定する
  （Day-1 デプロイで既に設定済み）。本番ではこの経路を推奨する。
- **Web Settings タブ** — ダッシュボードの **Settings** タブでストレージモード `gcs`
  （バケット/プレフィックスとともに）を選択すると、その値が `.beacon_settings.json` に
  永続化される。BEACON 4.1.0 以降、この選択は **すべて** のデータ経路で尊重される —
  PIR と asset のロード/保存は、`BEACON_STORAGE` 環境変数が設定されていなくても
  Settings UI の選択を尊重するようになった。（以前のリリースでは、env 変数も併設しない
  限りデータロードで Settings 値が無視されていた。）

環境変数が優先順位の頂点にあるため、Cloud Run リビジョンに設定された `BEACON_STORAGE` は
Settings UI が保存した値を上書きする。したがって Cloud Run デプロイでは、リビジョンの
env 変数を権威とし、Settings タブは主にローカル/スタンドアロン実行で使うことを推奨する。

> **GCS アクセス要件:** ランタイムのサービスアカウント（`beacon-sa`）はバケットに対する
> `roles/storage.objectAdmin` を必要とし（Day-0 で付与）、バケットが存在し（Day-0）、
> イメージに `gcs` extra（`google-cloud-storage`）がインストールされている必要がある。
> これらが整っていれば、アナリスト側で認証情報を扱う必要はない — Cloud Run が
> サービスアカウントの identity を注入する。

### 詳細コマンド

同じフローを実コマンドで示す。CLI 呼び出しは `uv run` を使い、クロスリポジトリの手順は
兄弟ディレクトリ `../TRACE` / `../SAGE` のチェックアウトを前提とする。

```bash
# 1. ビジネスコンテキストの作成（入力文書を編集）
#    input/context.md  — 業種・地理・クラウンジュエル・規制要件

# 2. PIR + 3 つの asset ドラフトを生成（1 パス）
uv run beacon pir-generate                    # input/context.md を使用
#    pir_output.json と assets_<ts>.json / identity_assets_<ts>.json /
#    user_accounts_<ts>.json を生成。BEACON_STORAGE=gcs ならバケットに格納される。

# 3. ダッシュボードで閲覧・編集（LLM が補えない組織既知フィールド）
uv run beacon web                             # http://localhost:8000
#    PIR タブ      — スコアを確認し PIR を承認
#    Assets タブ   — owner / security_control_ids / security_controls /
#                    asset_vulnerabilities（CVE → asset_id）
#    Identity タブ — identity の説明・ロール・なりすましフラグ
#    Accounts タブ — アカウント種別・特権フラグ・account_on_asset エッジ
#    Settings タブ — ストレージモード / bucket / prefix・SAGE URL・TRACE path
#    各タブを再保存すると新しい <type>_<ts>.json がバックエンドに書き込まれる。

# 4. すべての SAGE 入力を TRACE（単一の検証ゲート）で検証
cd ../TRACE && uv run trace validate-pir --pir pir_output.json
cd ../TRACE && uv run trace validate-pir --pir pir_output.json --assets assets.json

# 5. SAGE グラフへ取込
cd ../SAGE && uv run sage load-assets --input output/assets.json
cd ../SAGE && uv run sage run-etl

# 6. 攻撃経路のクエリ
cd ../SAGE && uv run sage visualize-graph     # インタラクティブ HTML
#    あるいはダッシュボードの Threats タブを使う（SAGE API プロキシ:
#    アクター検索・TTP 参照・threat-summary）。
```

各ステップの詳細（PIR フィールド、Assets タブ編集、ETL 検証、トラブルシューティング）は
[docs/usage.ja.md](usage.ja.md) と [docs/pipeline-guide.md](pipeline-guide.md) を参照すること。

---

## アクセス（本番推奨 = L2）

デプロイ時に `--no-allow-unauthenticated` が既に設定されている。アクセスが必要なアイデンティティに `roles/run.invoker` を付与する。

### 呼び出し権限の付与

```sh
# 個人ユーザー
gcloud run services add-iam-policy-binding beacon-web \
  --region=${REGION} \
  --member="user:alice@example.com" \
  --role=roles/run.invoker \
  --project=${GCP_PROJECT_ID}

# Google グループ（チーム利用に推奨）
gcloud run services add-iam-policy-binding beacon-web \
  --region=${REGION} \
  --member="group:beacon-users@example.com" \
  --role=roles/run.invoker \
  --project=${GCP_PROJECT_ID}
```

### ブラウザアクセス

```sh
gcloud run services proxy beacon-web --region=${REGION} --project=${GCP_PROJECT_ID}
# http://localhost:8080/dashboard を開く
```

proxy が開発者の identity token を自動注入するため、bearer token の管理は不要。

### curl による動作確認

```sh
URL=$(gcloud run services describe beacon-web \
  --region=${REGION} \
  --format='value(status.url)' \
  --project=${GCP_PROJECT_ID})

curl -sL -H "Authorization: Bearer $(gcloud auth print-identity-token)" \
  -w "\nHTTP=%{http_code}\n" \
  ${URL}/dashboard | head -10
```

期待結果: `HTTP=200` かつ `<title>BEACON — Dashboard</title>` を含む HTML。

### SAGE 連携（クロスリポジトリ）

BEACON のサービスアカウント（`beacon-sa`）が SAGE Analysis API を呼び出すには、`sage-api` に対して `roles/run.invoker` が必要である。SAGE 側から付与する:

```sh
gcloud run services add-iam-policy-binding sage-api \
  --region=${REGION} \
  --member="serviceAccount:beacon-sa@${GCP_PROJECT_ID}.iam.gserviceaccount.com" \
  --role=roles/run.invoker \
  --project=${GCP_PROJECT_ID}
```

SAGE の完全なデプロイ手順は [SAGE deploy.md](../../sage/docs/deploy.md) を参照すること。

---

## 対象外

IAP / 内部ロードバランサ / VPC Service Controls はこのガイドでは設定しない。少数の Google Workspace ユーザー運用（数名程度）では、上記の L2 IAM バインディングで十分である。コンテキストアウェアアクセスやカスタムネットワーク構成が必要な場合は https://cloud.google.com/iap/docs を参照すること。

---

## CTI Platform console トポロジ（ブラウザ完結運用の推奨）

Collection が TRACE を呼び、Threats が SAGE を呼ぶブラウザワークフローでは、
BEACON web と TRACE CLI を 1 つのイメージに同梱した **CTI Platform** Cloud Run service
をデプロイする。SAGE ETL は単一 writer の Cloud Run Job として分離し、`sage-api` は
読み取り専用 Analysis API として動かす。

推奨コンポーネント:

| コンポーネント | Cloud Run 種別 | 用途 |
|---------------|----------------|------|
| `cti-console` | service | BEACON web UI + TRACE CLI subprocess (`TRACE_ROOT_PATH=/app/trace`) |
| `sage-api` | service | Threats タブが利用する読み取り専用 SAGE Analysis API |
| `sage-etl` | job | 共有 GCS storage の `db/sage.db` を更新する単一 writer ETL |

統合 console image はリポジトリルート（`beacon/` と `trace/` の1階層上）からビルドする:

```bash
export IMAGE=${REGION}-docker.pkg.dev/${GCP_PROJECT_ID}/cloud-run/cti-console

gcloud builds submit . \
  --config=beacon/cloudbuild.cti-console.yaml \
  --ignore-file=beacon/.gcloudignore.cti-console \
  --substitutions=_IMAGE=${IMAGE} \
  --project=${GCP_PROJECT_ID}
```

SAGE API URL と共有 storage 設定を指定して console service をデプロイする:

```bash
gcloud run deploy cti-console \
  --image=${IMAGE} \
  --region=${REGION} \
  --project=${GCP_PROJECT_ID} \
  --service-account="beacon-web@${GCP_PROJECT_ID}.iam.gserviceaccount.com" \
  --set-env-vars="TRACE_ROOT_PATH=/app/trace,SAGE_API_URL=${SAGE_API_URL},BEACON_STORAGE=gcs,BEACON_STORAGE_BUCKET=${STORAGE_BUCKET},BEACON_STORAGE_PREFIX=${STORAGE_PREFIX}"
```

`TRACE_ROOT_PATH=/app/trace` はイメージ内で既定設定され、必要なら上書きできる。
Collection から TRACE を実行しない構成では、従来の BEACON 単体 image も利用できる。
