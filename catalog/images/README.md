# Marketplace 離線 Image Tars

放置各 catalog 項目的 docker image tar 檔(離線「安裝」用)。

- 檔名約定:`<catalog_id>.tar`(如 `perplexity-ask.tar`);
  也可在 catalog yaml 以 `image_tar:` 覆寫檔名,並可用 `{tag}` / `{image}` / `{id}` 佔位符,
  例如 `image_tar: my-mcp_{tag}.tar.gz` —— 升版只改 `docker.tag`,檔名自動跟著變。
- 支援 gzip 壓縮(`.tar.gz`),docker load 原生可讀,不必解壓。
- 產生方式:`docker save -o <catalog_id>.tar <image>:<tag>`
- 「安裝」= 後端以 docker SDK 載入此 tar(等同 `docker load -i`);
  「部署」= 啟動 container(image 必須已安裝)。
