#!/bin/bash

pwd
url=$1
mp4=${2:-latest.mp4}
m3u8=$(curl -s "$url")
KEY=$(echo "$m3u8" | grep EXT-X-KEY | cut -d'"' -f2 | xargs curl -sL | xxd -p -c 32)
KIV=$(echo "$m3u8" | grep -oP 'IV=0x\w+' | sed 's/IV=0x//')
whitelist="pipe,file,https,tls,tcp,crypto,concat"
temp="temp_segs.txt"

i=0
for line in $(echo "$m3u8" | grep -v '^#'); do
  echo "$i $line"
  seg="temp_$i.mp4"
  ffmpeg -loglevel warning -y \
    -protocol_whitelist "$whitelist" \
    -decryption_key "$KEY" -decryption_iv "$KIV" \
    -i "crypto+$line" \
    -c copy "$seg"
  if [ -f "$seg" ]; then
    echo "file '$seg'" >> $temp
  fi
  ((i++))
done

ffmpeg -loglevel warning -y \
  -protocol_whitelist "$whitelist" \
  -f concat -safe 0 \
  -i "$temp" \
  -c copy "$mp4"
rm -vf temp_*