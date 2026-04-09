#!/bin/bash
# getedge-dev.sh - 开发环境安装脚本

set -euo pipefail

### --- 配置 --- ###
IMAGE_NAME="orchestrator-agent:dev"
NETMON_IMAGE_NAME="autonomy-netmon:latest"
CONTAINER_NAME="dev_orchestrator_agent"
NETMON_CONTAINER_NAME="dev_netmon"
SHARED_VOLUME="orchestrator-shared"

# 开发环境配置
DEV_SERVER_URL="localhost:3001"  # 您的 NestJS 开发服务器
DEV_DEVICE_ID="dev-$(hostname)-$(date +%s)"

echo "=== 开发环境安装（跳过 mTLS）==="

### --- 检查依赖 --- ###
echo "检查依赖..."
for cmd in curl docker; do
    if ! command -v "$cmd" &>/dev/null; then
        echo "[ERROR] 缺少依赖: $cmd"
        exit 1
    fi
done

### --- 创建共享卷 --- ###
echo "创建共享卷..."
if ! docker volume inspect "$SHARED_VOLUME" &>/dev/null; then
    docker volume create "$SHARED_VOLUME"
    echo "[SUCCESS] 共享卷已创建"
else
    echo "[SUCCESS] 共享卷已存在"
fi

### --- 部署网络监控 --- ###
echo "部署网络监控容器..."
if docker ps -a --format '{{.Names}}' | grep -q "^${NETMON_CONTAINER_NAME}$"; then
    echo "移除现有的网络监控容器..."
    docker rm -f "$NETMON_CONTAINER_NAME"
fi

docker run -d \
  --name "$NETMON_CONTAINER_NAME" \
  --network=host \
  --pid=host \
  --privileged \
  --restart unless-stopped \
  -v "$SHARED_VOLUME:/var/orchestrator" \
  -v /dev:/dev \
  -v /run/udev:/run/udev:ro \
  "$NETMON_IMAGE_NAME"

echo "[SUCCESS] 网络监控容器已启动"

### --- 部署 orchestrator-agent --- ###
echo "部署 orchestrator-agent 容器..."

# 停止并移除现有容器
if docker ps -a --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
    echo "移除现有的 orchestrator-agent 容器..."
    docker rm -f "$CONTAINER_NAME"
fi

# 创建开发环境配置目录
mkdir -p /tmp/orchestrator-dev
echo "$DEV_DEVICE_ID" > /tmp/orchestrator-dev/device-id
echo "$DEV_SERVER_URL" > /tmp/orchestrator-dev/server-url

# 运行开发版容器（跳过 mTLS）
docker run -d \
  --name "$CONTAINER_NAME" \
  --restart unless-stopped \
  -v /var/run/docker.sock:/var/run/docker.sock \
  -v "$SHARED_VOLUME:/var/orchestrator" \
  -v /tmp/orchestrator-dev:/tmp/orchestrator-dev \
  -e DEV_MODE=true \
  -e SERVER_URL="$DEV_SERVER_URL" \
  -e DEVICE_ID="$DEV_DEVICE_ID" \
  "$IMAGE_NAME"

echo "=== 开发环境安装完成 ==="
echo "设备ID: $DEV_DEVICE_ID"
echo "服务器: $DEV_SERVER_URL"
echo ""
echo "下一步："
echo "1. 在 NestJS 中配置设备ID: $DEV_DEVICE_ID"
echo "2. 启动 NestJS WebSocket 服务在端口 3001"
echo "3. 测试连接和功能"