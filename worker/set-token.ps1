# 合言葉(ADMIN_TOKEN)を作って Cloudflare に設定し、控えをファイルに残す。
#
# 使い方: このファイルを右クリック →「PowerShell で実行」
#         または PowerShell で次を実行
#           powershell -ExecutionPolicy Bypass -File "set-token.ps1"
#
# 合言葉は画面に表示されません。控えは下の $tokenFile に保存されます。
# 保存先はリポジトリの外なので、GitHub には上がりません。

$ErrorActionPreference = "Stop"
Set-Location -Path $PSScriptRoot

$tokenFile = "C:\Users\Hibiki\OneDrive\ドキュメント\maai-admin-token.txt"

Write-Host "合言葉を作っています..."
$bytes = New-Object byte[] 24
[System.Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($bytes)
$token = [Convert]::ToBase64String($bytes).Replace('+','-').Replace('/','_').Replace('=','')

Write-Host "Cloudflare に設定しています..."
$token | npx --yes wrangler secret put ADMIN_TOKEN | Out-Null

if ($LASTEXITCODE -ne 0) {
  Write-Host "失敗しました。上のエラーを Claude に伝えてください。" -ForegroundColor Red
  exit 1
}

$body = @"
間合い — 意見を読むための合言葉

合言葉: $token

読むときのコマンド（PowerShell）:
  curl.exe -H "Authorization: Bearer $token" https://maai-feedback.jaykim-can.workers.dev/admin/list

このファイルは他人に見せないでください。
$(Get-Date -Format 'yyyy-MM-dd HH:mm') 作成
"@
$body | Out-File -FilePath $tokenFile -Encoding utf8

Write-Host ""
Write-Host "完了しました。" -ForegroundColor Green
Write-Host "控えの場所: $tokenFile"
Write-Host "読むときのコマンドも、そのファイルに書いてあります。"
