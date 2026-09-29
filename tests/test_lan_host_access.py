"""本机局域网地址自动放行的回归测试（Invalid host header 修复）。

背景：e1195dc 收紧 TrustedHostMiddleware/local_write_guard 后只认回环地址，从本机
局域网 IP 打开工作台会被拒成 400 Invalid host header / 写请求 403。修复方式是启动时
自动放行本机自己的网卡 IP 与主机名（见 web/app.py `_own_lan_hosts`）。

运行：pytest tests/test_lan_host_access.py -q
"""
from __future__ import annotations

import ipaddress
import socket

import pytest
from fastapi.testclient import TestClient

from web import app as web

LOOPBACK = ('127.0.0.1', 51234)


def test_own_lan_hosts_are_non_loopback_ipv4():
    for h in web._own_lan_hosts():
        ip = ipaddress.ip_address(h)   # 非法字符串会抛 ValueError
        assert ip.version == 4
        assert not ip.is_loopback


def test_own_hosts_wired_into_middleware_lists():
    """探测到的每个本机地址都进 _EXTRA_HOSTS（TrustedHost）与 _LOCAL_ORIGINS（写守卫/CORS）。"""
    for h in web._own_lan_hosts():
        assert h in web._EXTRA_HOSTS
        assert f'http://{h}:7860' in web._LOCAL_ORIGINS


def _probe(host: str) -> int:
    """带指定 Host 头探一个不存在的路径：403/400 = 被中间件拦，404 = 放行到路由。"""
    client = TestClient(web.app, base_url='http://127.0.0.1:7860', client=LOOPBACK)
    r = client.get('/api/__lan_probe__', headers={'Host': host})
    return r.status_code


def test_foreign_host_still_rejected():
    """陌生域名（DNS rebinding 形态）仍被 TrustedHostMiddleware 拒绝。"""
    assert _probe('evil.example') == 400


@pytest.mark.parametrize('host', [web._own_lan_hosts()[0] if web._own_lan_hosts() else '127.0.0.1',
                                  socket.gethostname().lower()])
def test_own_host_headers_allowed(host):
    """本机地址（有网卡 IP 时取第一个，否则回环兜底）与主机名的 Host 头必须放行。"""
    assert _probe(host) == 404
