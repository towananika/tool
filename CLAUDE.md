# 間合い（tool）開発ルール

日本語で簡潔に。結論→根拠→補足。

## 構成
- `index.html`（約6400行）: タイマーとカウンター。ほかに `about.html` `clarity.html` `jeonse.html` など独立ページ
- `sw.js`: service worker（キャッシュ優先）。公開: https://towananika.github.io/tool/
- 音の聴き比べ・実測: `Triathlon/tools/counter_accent.html`

## トークン節約
- **index.html を全文読まない。** Grep で行を引き、`Read(offset, limit)` で必要な範囲だけ読む
  - カウンターの音: `function (playClick|playMilestone|knockV|woodRing|counterOut)`、音色 `var VOICES`、音量 `COUNTER_VOL`
  - カウンターの状態: `counterState`
- 互いに関係ない読み取り・編集は1回の応答にまとめる

## 必ず守る
- **index.html など中身を変えたら、同じコミットで `sw.js` の `CACHE_NAME` の番号を +1**
  （忘れると端末は古い版を出し続ける。2026-09-15 に実際に起きた）
- **その番号を上げたら、`CHANGELOG.md` の「sw キャッシュ番号ログ」に1行足す**
  （2026-09-16 Hibiki指定。細かい変更も、あとから「どの版で何が変わったか」を探せるように）
- 音は Claude が聴けない。変えたら Hibiki に聴いてもらう（ローカル: `python -m http.server 8898 --bind 127.0.0.1`）
- 構文確認: `<script>` を抜き出して `node --check`

## 公開
- push は Hibiki が「プッシュして」と言ったときだけ。`git pull --rebase` → `git push`
- 反映確認はキャッシュを避けて取る（`?nocache=時刻` と `cache:"no-store"`、または curl）
- 報告は「公開ファイルに入った」と「端末では開き直しが1回要る」を分けて書く
