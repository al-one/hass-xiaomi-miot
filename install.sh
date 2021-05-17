#!/bin/bash
# wget -q -O - https://raw.fastgit.org/al-one/hass-xiaomi-miot/master/install.sh | bash -
set -e

[ -z "$DOMAIN" ] && DOMAIN="xiaomi_miot"
[ -z "$REPO_PATH" ] && REPO_PATH="al-one/hass-xiaomi-miot"
REPO_NAME=$(basename "$REPO_PATH")

[ -z "$ARCHIVE_TAG" ] && ARCHIVE_TAG="$1"
[ -z "$ARCHIVE_TAG" ] && ARCHIVE_TAG="master"
ARCHIVE_URL="https://github.com/$REPO_PATH/archive/$ARCHIVE_TAG.zip"

RED_COLOR='\033[0;31m'
GREEN_COLOR='\033[0;32m'
GREEN_YELLOW='\033[1;33m'
NO_COLOR='\033[0m'

declare haPath
declare ccPath
declare -a paths=(
    "$PWD"
    "$PWD/config"
    "/config"
    "$HOME/.homeassistant"
    "/usr/share/hassio/homeassistant"
)

function info () { echo -e "${GREEN_COLOR}INFO: $1${NO_COLOR}";}
function warn () { echo -e "${GREEN_YELLOW}WARN: $1${NO_COLOR}";}
function error () { echo -e "${RED_COLOR}ERROR: $1${NO_COLOR}"; if [ "$2" != "false" ]; then exit 1;fi; }

function checkRequirement () {
    if [ -z "$(command -v "$1")" ]; then
        error "'$1' is not installed"
    fi
}

checkRequirement "wget"
checkRequirement "unzip"

info "Archive URL: $ARCHIVE_URL"
info "Trying to find the correct directory..."
for path in "${paths[@]}"; do
    if [ -n "$haPath" ]; then
        break
    fi

    if [ -f "$path/home-assistant.log" ]; then
        haPath="$path"
    else
        if [ -d "$path/.storage" ] && [ -f "$path/configuration.yaml" ]; then
            haPath="$path"
        fi
    fi
done

if [ -n "$haPath" ]; then
    info "Found Home Assistant configuration directory at '$haPath'"
    cd "$haPath" || error "Could not change path to $haPath"
    ccPath="$haPath/custom_components"
    if [ ! -d "$ccPath" ]; then
        info "Creating custom_components directory..."
        mkdir "$ccPath"
    fi

    info "Changing to the custom_components directory..."
    cd "$ccPath" || error "Could not change path to $ccPath"

    info "Downloading..."
    wget -t 2 -O "$ccPath/$ARCHIVE_TAG.zip" "$ARCHIVE_URL"

    if [ -d "$ccPath/$DOMAIN" ]; then
        warn "custom_components/$DOMAIN directory already exist, cleaning up..."
        rm -R "$ccPath/$DOMAIN"
    fi

    info "Unpacking..."
    unzip "$ccPath/$ARCHIVE_TAG.zip" -d "$ccPath" >/dev/null 2>&1

    ver=${ARCHIVE_TAG/#v/}
    cp -rf "$ccPath/$REPO_NAME-$ver/custom_components/$DOMAIN" "$ccPath"

    info "Removing temp files..."
    rm -rf "$ccPath/$ARCHIVE_TAG.zip"
    rm -rf "$ccPath/$REPO_NAME-$ver"
    info "Installation complete."
    info "安装成功！"
    echo
    info "Remember to restart Home Assistant before you configure it."
    info "请重启 Home Assistant"

else
    echo
    error "Could not find the directory for Home Assistant" false
    echo "Manually change the directory to the root of your Home Assistant configuration"
    echo "With the user that is running Home Assistant"
    echo "and run the script again"
    exit 1
fi
