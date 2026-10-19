#!/bin/bash
# Fetch the device ID and local key of the devices in your Eufy account. Run once.
#
# This is the only part of the project that talks to the cloud: it signs in with your
# Eufy account, opens the Tuya session the Eufy app uses behind the scenes and lists
# the devices with their local keys. Nothing is stored; email and password are asked
# for interactively.
#
# Needs only tools that ship with macOS 15 or later: bash, curl, openssl, bc, jq, xxd.
set -euo pipefail

EUFY_LOGIN_URL="https://home-api.eufylife.com/v1/user/email/login"
EUFY_CLIENT_ID="eufyhome-app"
EUFY_CLIENT_SECRET="GQCpr9dSp3uQpsOMgJ4xQ"
EUFY_COUNTRY="NL"
EUFY_TIMEZONE="Europe/Amsterdam"

TUYA_URL="https://a1.tuyaeu.com" # replaced by the account's region after login
TUYA_CLIENT_ID="yx5v9uc3ef9wg3v9atje"
TUYA_APP_SECRET="s8x78u7xwymasd9kqa7a73pjhxqsedaj"
TUYA_BMP_SECRET="cepev5pfnhua4dkqkdpmnrdxx378mpjr"
TUYA_SIGN_KEY="A_${TUYA_BMP_SECRET}_${TUYA_APP_SECRET}"
# The Tuya account behind an Eufy account has a password derived from its uid.
TUYA_PASSWORD_AES_KEY="244e6d8a56ac879124432d8b6cbca2c4"
TUYA_PASSWORD_AES_IV="772456f2a7664cf3392c3597e93e5747"
SIGNED_PARAMS=" a v lat lon lang deviceId appVersion ttid isH5 h5Token os clientId postData time requestId et n4h5 sid sp "

for tool in curl openssl bc jq xxd uuidgen; do
  command -v "$tool" >/dev/null || { echo "Ontbreekt: $tool" >&2; exit 1; }
done

fail() {
  echo "" >&2
  echo "Mislukt: $*" >&2
  exit 1
}

md5_hex() { printf '%s' "$1" | openssl dgst -md5 -r | cut -d' ' -f1; }

# MD5 with its four 8-character groups reordered, as the Tuya signature expects.
md5_shuffled() {
  local h
  h=$(md5_hex "$1")
  printf '%s' "${h:8:8}${h:0:8}${h:24:8}${h:16:8}"
}

hmac_sha256() { printf '%s' "$2" | openssl dgst -sha256 -hmac "$1" -r | cut -d' ' -f1; }

uri() { jq -rn --arg v "$1" '$v | @uri'; }

# Sign "key=value" arguments: the signed keys, sorted, joined with "||", HMAC-SHA256.
tuya_sign() {
  local message="" line key value
  while IFS= read -r line; do
    key=${line%%=*}
    value=${line#*=}
    case "$SIGNED_PARAMS" in *" $key "*) ;; *) continue ;; esac
    [ "$key" = postData ] && value=$(md5_shuffled "$value")
    message="${message:+$message||}$key=$value"
  done < <(printf '%s\n' "$@" | LC_ALL=C sort)
  hmac_sha256 "$TUYA_SIGN_KEY" "$message"
}

# Zero-padded to a multiple of 16, AES-128-CBC without padding, upper hex, MD5.
tuya_password() {
  local uid=$1 size padded encrypted
  size=$(((${#uid} + 15) / 16 * 16))
  padded=$(printf "%${size}s" "$uid" | tr ' ' 0)
  encrypted=$(printf '%s' "$padded" |
    openssl enc -aes-128-cbc -K "$TUYA_PASSWORD_AES_KEY" -iv "$TUYA_PASSWORD_AES_IV" -nopad |
    xxd -p | tr -d '\n' | tr 'a-f' 'A-F')
  md5_hex "$encrypted"
}

# Raw RSA: plaintext^exponent mod modulus, as lower hex of the modulus' byte length.
rsa_encrypt_hex() {
  local plaintext=$1 modulus=$2 exponent=$3 plain_hex plain_dec mod_hex result width
  plain_hex=$(printf '%s' "$plaintext" | xxd -p | tr -d '\n' | tr 'a-f' 'A-F')
  plain_dec=$(BC_LINE_LENGTH=0 bc <<<"ibase=16; $plain_hex")
  mod_hex=$(BC_LINE_LENGTH=0 bc <<<"obase=16; $modulus")
  result=$(
    # macOS bc only accepts single-letter names: p is modular exponentiation.
    BC_LINE_LENGTH=0 bc <<EOF
define p(b, e, m) {
  auto r
  r = 1
  b = b % m
  while (e > 0) {
    if (e % 2 == 1) r = (r * b) % m
    e = e / 2
    b = (b * b) % m
  }
  return (r)
}
obase = 16
p($plain_dec, $exponent, $modulus)
EOF
  )
  width=$(((${#mod_hex} + 1) / 2 * 2))
  printf "%${width}s" "$result" | tr ' ' 0 | tr 'A-F' 'a-f'
}

# The Eufy app's request profile.
eufy_curl() {
  curl -sS -H "User-Agent: EufyHome-Android-3.1.3-753" -H "category: Home" -H "clientType: 2" \
    -H "language: en" -H "country: $EUFY_COUNTRY" -H "timezone: $EUFY_TIMEZONE" \
    -H "openudid: sdk_gphone64_arm64" "$@"
}

tuya_origin() {
  case "$1" in
    EU) echo "https://a1.tuyaeu.com" ;;
    AZ) echo "https://a1.tuyaus.com" ;;
    AY) echo "https://a1.tuyacn.com" ;;
    IN) echo "https://a1.tuyain.com" ;;
    *) fail "onbekende Tuya-regio '$1'" ;;
  esac
}

TUYA_SID=""
TUYA_DEVICE_ID="8534c8ec0ed0$(openssl rand -hex 16)"

# tuya_call ACTION VERSION POSTDATA [key=value ...] -> prints the "result" JSON.
tuya_call() {
  local action=$1 version=$2 post=$3 query="" pair sign reply
  shift 3
  local params=(
    "a=$action" "v=$version" "appVersion=2.4.0" "clientId=$TUYA_CLIENT_ID"
    "deviceId=$TUYA_DEVICE_ID" "et=0.0.1" "lang=en" "os=Android" "osSystem=12"
    "platform=sdk_gphone64_arm64" "requestId=$(uuidgen | tr 'A-Z' 'a-z')"
    "sdkVersion=3.0.8cAnker" "time=$(date +%s)" "timeZoneId=$EUFY_TIMEZONE" "ttid=android"
    "$@"
  )
  [ -n "$TUYA_SID" ] && params+=("sid=$TUYA_SID")
  if [ -n "$post" ]; then
    sign=$(tuya_sign "${params[@]}" "postData=$post")
  else
    sign=$(tuya_sign "${params[@]}")
  fi
  for pair in "${params[@]}" "sign=$sign"; do
    query="${query:+$query&}${pair%%=*}=$(uri "${pair#*=}")"
  done
  if [ -n "$post" ]; then
    reply=$(curl -sS -X POST "$TUYA_URL/api.json?$query" \
      -H "User-Agent: TY-UA=APP/Android/2.4.0/SDK/null" --data-urlencode "postData=$post")
  else
    reply=$(curl -sS -X POST "$TUYA_URL/api.json?$query" \
      -H "User-Agent: TY-UA=APP/Android/2.4.0/SDK/null" -d "")
  fi
  if ! jq -e 'has("result")' >/dev/null 2>&1 <<<"$reply"; then
    fail "$action: $(jq -r '"\(.errorCode) \(.errorMsg)"' <<<"$reply" 2>/dev/null || echo "$reply")"
  fi
  jq -c '.result' <<<"$reply"
}

main() {
  local email password login uid country tuya_uid challenge encrypted session gid devices homes
  local home_host settings region
  read -rp "Eufy e-mail: " email
  read -rsp "Eufy wachtwoord: " password
  echo ""

  login=$(eufy_curl -X POST "$EUFY_LOGIN_URL" -H "Content-Type: application/json" \
    -d "$(jq -nc --arg id "$EUFY_CLIENT_ID" --arg secret "$EUFY_CLIENT_SECRET" \
      --arg email "$email" --arg password "$password" \
      '{client_id: $id, client_Secret: $secret, email: $email, password: $password}')")
  unset password
  jq -e 'has("access_token")' >/dev/null 2>&1 <<<"$login" ||
    fail "Eufy-login: $(jq -r '.msg // .message // .' <<<"$login" 2>/dev/null || echo "$login")"
  uid=$(jq -r '.user_info.id' <<<"$login")
  country=$(jq -r '.user_info.phone_code // "31" | tostring' <<<"$login")
  tuya_uid="eh-$uid"

  # The account's settings name the Tuya region its devices live in.
  home_host=$(jq -r '.user_info.request_host // "https://api.eufylife.com"' <<<"$login")
  home_host=$(sed -E 's#^(https://[^/]+).*#\1#' <<<"$home_host")
  settings=$(eufy_curl "$home_host/v1/user/setting" \
    -H "token: $(jq -r '.access_token' <<<"$login")" -H "id: $uid")
  region=$(jq -r '.setting.home_setting.tuya_home.tuya_region_code // "EU"' <<<"$settings" 2>/dev/null ||
    echo EU)
  TUYA_URL=$(tuya_origin "$region")

  challenge=$(tuya_call tuya.m.user.uid.token.create 1.0 \
    "$(jq -nc --arg uid "$tuya_uid" --arg cc "$country" '{uid: $uid, countryCode: $cc}')")
  encrypted=$(rsa_encrypt_hex "$(tuya_password "$tuya_uid")" \
    "$(jq -r '.publicKey' <<<"$challenge")" "$(jq -r '.exponent' <<<"$challenge")")
  session=$(tuya_call tuya.m.user.uid.password.login.reg 1.0 \
    "$(jq -nc --arg uid "$tuya_uid" --arg cc "$country" --arg pw "$encrypted" \
      --arg token "$(jq -r '.token' <<<"$challenge")" \
      '{uid: $uid, countryCode: $cc, createGroup: true, ifencrypt: 1, passwd: $pw,
        options: "{\"group\": 1}", token: $token}')")
  TUYA_SID=$(jq -r '.sid' <<<"$session")
  TUYA_URL=$(jq -r '.domain.mobileApiUrl' <<<"$session")

  devices="[]"
  homes=$(tuya_call tuya.m.location.list 2.1 "")
  while IFS= read -r gid; do
    [ -n "$gid" ] || continue
    devices=$(jq -c -s 'add' <<<"$devices $(tuya_call tuya.m.my.group.device.list 1.0 "" "gid=$gid")")
  done < <(jq -r '.[]? | (.groupId // .locationId // empty) | tostring' <<<"$homes")
  devices=$(jq -c -s 'map(. // []) | add' <<<"$devices $(tuya_call tuya.m.my.shared.device.list 1.0 "")")

  jq -e 'map(select(.localKey)) | length > 0' >/dev/null <<<"$devices" ||
    fail "geen apparaten met een local key gevonden"
  jq -r 'map(select(.localKey)) | unique_by(.devId)[] |
    "\nnaam       \(.name)\nproduct    \(.productId)\ndevice_id  \(.devId)\nlocal_key  \(.localKey)"' \
    <<<"$devices"
  echo ""
  echo "Vul device_id en local_key in bij de integratie; het IP-adres zie je in je router."
}

if [ "${1:-}" = "--self-test" ]; then
  # Intermediate values for fixed inputs, compared against reference values in the tests.
  tuya_password "eh-0123456789abcdef0123456789abcdef01234567"
  tuya_sign "a=tuya.m.location.list" "v=2.1" "time=1700000000" "lang=en" "os=Android" \
    'postData={"uid":"x"}' "osSystem=12" "sid=s"
  rsa_encrypt_hex "0123456789abcdef0123456789abcdef" \
    "$(BC_LINE_LENGTH=0 bc <<<'2^1023 + 1234567')" 65537
  exit 0
fi

main
