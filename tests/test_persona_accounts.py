"""多画像多账号：按画像隔离的凭证命名空间回归测试（不启动真实浏览器）。

钉住的契约：
* 路径助手——画像 X 的登录态/cookie/发布状态都在画像专属子目录，通用模式与历史路径一致；
* 登录标记 / 登录态判定 / 二维码相对路径按画像隔离，互不串号；
* whoami 缓存与登录进程表键为 (platform, persona)；
* 登出、删除画像只清自己命名空间；
* 带非法/不存在画像参数的接口 400/404，不带画像时行为与旧版一致。
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient

from web import app as web

LOOPBACK = ('127.0.0.1', 51234)


@pytest.fixture()
def tmp_ns(tmp_path, monkeypatch):
    """把所有凭证落盘位置指到临时目录，测试不碰真实登录态。"""
    monkeypatch.setattr(web, 'PROJECT_ROOT', tmp_path)
    monkeypatch.setattr(web, 'OUTPUTS_DIR', tmp_path / 'outputs')
    monkeypatch.setattr(web, 'LOGIN_DIR', tmp_path / 'outputs' / '_login')
    monkeypatch.setattr(web, 'PUBLISH_DIR', tmp_path / 'outputs' / '_publish')
    monkeypatch.setattr(web, 'BROWSER_PROFILES', tmp_path / 'browser-profiles')
    monkeypatch.setattr(web, 'PROFILES_DIR', tmp_path / 'profiles')
    monkeypatch.setattr(web, 'profile_exists', lambda name: name == 'P1')
    monkeypatch.setattr(web, '_WHOAMI_CACHE', {})
    monkeypatch.setattr(web, 'LOGIN_PROCESSES', {})
    return tmp_path


# ---------------------------------------------------------------- 路径助手
def test_path_helpers_persona_vs_global(tmp_ns):
    assert web._persona_browser_root('P1') == tmp_ns / 'browser-profiles' / 'P1'
    assert web._persona_browser_root('') == tmp_ns / 'browser-profiles'
    assert web._persona_browser_root(None) == tmp_ns / 'browser-profiles'
    assert web._persona_login_dir('P1') == tmp_ns / 'outputs' / '_login' / 'P1'
    assert web._persona_login_dir(None) == tmp_ns / 'outputs' / '_login'
    assert web._persona_publish_dir('P1') == tmp_ns / 'outputs' / '_publish' / 'P1'
    # B 站 cookie：画像放画像根下，通用模式保持历史位置（仓库根 cookies.json）
    assert web._bili_cookie_path('P1') == tmp_ns / 'browser-profiles' / 'P1' / 'cookies-bilibili.json'
    assert web._bili_cookie_path(None) == tmp_ns / 'cookies.json'
    # 公众号 yaml 账号 key（@ 在文件名合法，token 缓存文件名无需转义）
    assert web._wechat_account_key('P1') == 'web@P1'
    assert web._wechat_account_key(None) == 'web'


def test_checked_persona_validation(tmp_ns):
    assert web._checked_persona('') == ''
    assert web._checked_persona(None) == ''
    assert web._checked_persona('  ') == ''
    assert web._checked_persona('P1') == 'P1'
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as e:
        web._checked_persona('no/such')
    assert e.value.status_code == 400
    with pytest.raises(HTTPException) as e:
        web._checked_persona('不存在')
    assert e.value.status_code == 404


# ------------------------------------------------------- 登录标记 / 状态隔离
def test_login_marker_isolated_per_persona(tmp_ns):
    web._write_login_marker('xiaohongshu', 'success', 'ok', 'P1')
    assert (tmp_ns / 'outputs' / '_login' / 'P1' / 'xiaohongshu.json').is_file()
    # 画像已登录 ≠ 通用模式已登录
    cfg = {'backend': 'web'}
    assert web._account_logged_in('xiaohongshu', cfg, 'P1') is True
    assert web._account_logged_in('xiaohongshu', cfg) is False
    # 通用模式的标记也不影响画像
    web._write_login_marker('xiaohongshu', 'success', 'ok')
    assert (tmp_ns / 'outputs' / '_login' / 'xiaohongshu.json').is_file()
    assert web._account_logged_in('xiaohongshu', cfg) is True


def test_biliup_cookie_isolated_per_persona(tmp_ns):
    cfg = {'backend': 'biliup'}
    assert web._account_logged_in('bilibili', cfg, 'P1') is False
    web._bili_cookie_path('P1').parent.mkdir(parents=True)
    web._bili_cookie_path('P1').write_text('{}')
    assert web._account_logged_in('bilibili', cfg, 'P1') is True
    assert web._account_logged_in('bilibili', cfg) is False


def test_login_status_qr_relative_path(tmp_ns):
    d = tmp_ns / 'outputs' / '_login' / 'P1'
    d.mkdir(parents=True)
    (d / 'xiaohongshu.png').write_bytes(b'png')
    s = web._login_status('xiaohongshu', 'P1')
    assert s['qr'] == '_login/P1/xiaohongshu.png'
    # 通用模式的二维码路径保持旧格式（前端 mediaUrl 直接用这个相对路径）
    (tmp_ns / 'outputs' / '_login' / 'xiaohongshu.png').write_bytes(b'png')
    assert web._login_status('xiaohongshu')['qr'] == '_login/xiaohongshu.png'


def test_logout_only_purges_own_namespace(tmp_ns):
    prof_dir = tmp_ns / 'browser-profiles' / 'P1' / 'XiaohongshuProfile'
    prof_dir.mkdir(parents=True)
    global_prof = tmp_ns / 'browser-profiles' / 'XiaohongshuProfile'
    global_prof.mkdir(parents=True)
    web._write_login_marker('xiaohongshu', 'success', 'ok', 'P1')
    web._write_login_marker('xiaohongshu', 'success', 'ok')
    client = TestClient(web.app, base_url='http://127.0.0.1:7860', client=LOOPBACK)
    r = client.post('/api/logout/xiaohongshu', params={'persona': 'P1'})
    assert r.status_code == 200, r.text
    assert not prof_dir.exists()
    assert (tmp_ns / 'outputs' / '_login' / 'P1' / 'xiaohongshu.json').exists() is False
    # 通用命名空间原封不动
    assert global_prof.is_dir()
    assert (tmp_ns / 'outputs' / '_login' / 'xiaohongshu.json').is_file()


def test_logout_wechat_oa_clears_persona_account(tmp_ns, monkeypatch):
    monkeypatch.setattr(web, 'WECHAT_CONFIG_YAML', tmp_path_yaml(tmp_ns))
    monkeypatch.setattr(web, 'WECHAT_SKILL_SCRIPTS', tmp_ns / 'skill-scripts')
    d = tmp_ns / 'outputs' / '_login' / 'P1'
    d.mkdir(parents=True)
    (d / 'wechat-oa-mp.json').write_text(json.dumps({'state': 'success'}), encoding='utf-8')
    mp_prof = tmp_ns / 'browser-profiles' / 'P1' / 'WeixinMpProfile'
    mp_prof.mkdir(parents=True)
    client = TestClient(web.app, base_url='http://127.0.0.1:7860', client=LOOPBACK)
    r = client.post('/api/logout/wechat-oa', params={'persona': 'P1'})
    assert r.status_code == 200, r.text
    assert not mp_prof.exists()
    assert not (d / 'wechat-oa-mp.json').exists()


def tmp_path_yaml(root: Path) -> Path:
    """公众号 yaml 指到临时文件（不存在 → _wechat_load_yaml 安全返回空 dict）。"""
    return root / 'wechat-publisher.yaml'


# ---------------------------------------------------------------- 接口层
def test_api_accounts_persona_unknown_404(tmp_ns):
    client = TestClient(web.app, base_url='http://127.0.0.1:7860', client=LOOPBACK)
    assert client.get('/api/accounts').status_code == 200
    assert client.get('/api/accounts', params={'persona': 'P1'}).status_code == 200
    assert client.get('/api/accounts', params={'persona': 'ghost'}).status_code == 404


def test_login_sms_writes_persona_code_file(tmp_ns):
    client = TestClient(web.app, base_url='http://127.0.0.1:7860', client=LOOPBACK)
    r = client.post('/api/login/douyin/sms', params={'persona': 'P1'}, json={'code': '123456'})
    assert r.status_code == 200, r.text
    assert (tmp_ns / 'outputs' / '_login' / 'P1' / 'douyin.code').read_text(encoding='utf-8') == '123456'
    assert not (tmp_ns / 'outputs' / '_login' / 'douyin.code').exists()


def test_publish_sms_writes_persona_code_file(tmp_ns):
    client = TestClient(web.app, base_url='http://127.0.0.1:7860', client=LOOPBACK)
    r = client.post('/api/publish/douyin/sms', params={'persona': 'P1'}, json={'code': '123456'})
    assert r.status_code == 200, r.text
    assert (tmp_ns / 'outputs' / '_publish' / 'P1' / 'douyin.code').is_file()


def test_whoami_cache_keyed_by_platform_and_persona(tmp_ns, monkeypatch):
    """whoami 真校验的结果必须按 (platform, persona) 缓存，画像间不串号。"""
    fake = Mock()
    fake.returncode = 0
    fake.stdout = '{"loggedIn": true, "name": "画像账号", "avatar": ""}'
    fake.stderr = ''
    run_mock = Mock(return_value=fake)
    monkeypatch.setattr(web.subprocess, 'run', run_mock)
    client = TestClient(web.app, base_url='http://127.0.0.1:7860', client=LOOPBACK)
    r = client.get('/api/accounts/xiaohongshu/whoami', params={'persona': 'P1'})
    assert r.status_code == 200, r.text
    assert r.json()['loggedIn'] is True
    # 缓存键是元组且只含画像命名空间
    assert ('xiaohongshu', 'P1') in web._WHOAMI_CACHE
    assert ('xiaohongshu', '') not in web._WHOAMI_CACHE
    # 子进程命令带了画像专属 --profile-base
    cmd = run_mock.call_args.args[0]
    assert '--profile-base' in cmd
    assert str(tmp_ns / 'browser-profiles' / 'P1') in cmd
    # 确认登录后，快速路径（_account_logged_in）在画像命名空间内读到 success
    assert web._account_logged_in('xiaohongshu', {'backend': 'xhs'}, 'P1') is True


def test_delete_persona_purges_credentials(tmp_ns, monkeypatch):
    monkeypatch.setattr(web, 'WECHAT_CONFIG_YAML', tmp_path_yaml(tmp_ns))
    (tmp_ns / 'profiles' / 'P1').mkdir(parents=True)
    (tmp_ns / 'profiles' / 'P1' / 'identity.md').write_text('# P1', encoding='utf-8')
    web._write_login_marker('xiaohongshu', 'success', 'ok', 'P1')
    (tmp_ns / 'browser-profiles' / 'P1' / 'XiaohongshuProfile').mkdir(parents=True)
    client = TestClient(web.app, base_url='http://127.0.0.1:7860', client=LOOPBACK)
    r = client.delete('/api/persona/P1')
    assert r.status_code == 200, r.text
    assert not (tmp_ns / 'browser-profiles' / 'P1').exists()
    assert not (tmp_ns / 'outputs' / '_login' / 'P1').exists()
    assert not (tmp_ns / 'profiles' / 'P1').exists()


def test_relogin_terminates_previous_runner(tmp_ns, monkeypatch):
    """同一画像命名空间重复点「登录」必须终止上一个 runner——两个 Chromium 抢同一
    user-data-dir 会日志交错/状态互踩（真机视频号：旧 runner 挂着差点覆盖 success 标记）。"""
    import asyncio as _asyncio

    procs = []

    def fake_popen(cmd, **kw):
        m = Mock()
        m.poll.return_value = None          # 永远「活着」
        m.terminate = Mock()
        m.wait = Mock()
        procs.append(m)
        return m

    monkeypatch.setattr(web.subprocess, 'Popen', fake_popen)
    # 轮询循环 50×0.5s：把 sleep 打成 no-op，测试秒回
    async def _fast_sleep(_s):
        return None
    monkeypatch.setattr(web.asyncio, 'sleep', _fast_sleep)
    client = TestClient(web.app, base_url='http://127.0.0.1:7860', client=LOOPBACK)
    r1 = client.post('/api/login/zhihu', params={'persona': 'P1'})
    assert r1.status_code == 200, r1.text
    r2 = client.post('/api/login/zhihu', params={'persona': 'P1'})
    assert r2.status_code == 200, r2.text
    procs[0].terminate.assert_called_once()   # 旧 runner 被终止
    assert web.LOGIN_PROCESSES[('zhihu', 'P1')] is procs[1]
    # 不同画像命名空间互不影响
    r3 = client.post('/api/login/zhihu')
    assert r3.status_code == 200, r3.text
    procs[1].terminate.assert_not_called()


def test_publish_request_accepts_persona_field(tmp_ns, monkeypatch):
    """PublishRequest.persona 非空时用画像账号（子进程参数带画像根）；校验失败路径不落盘。"""
    fake = Mock()
    fake.returncode = 0
    fake.stdout = '{"ok": true}'
    fake.stderr = ''
    run_mock = Mock(return_value=fake)
    monkeypatch.setattr(web.subprocess, 'run', run_mock)
    # 知乎属 web 后端且不强制媒体；标题/正文给足即可走到子进程
    client = TestClient(web.app, base_url='http://127.0.0.1:7860', client=LOOPBACK)
    r = client.post('/api/publish/zhihu', json={
        'title': 't', 'body': 'b', 'media': [], 'tags': '', 'persona': 'P1'})
    assert r.status_code == 200, r.text
    cmd = run_mock.call_args.args[0]
    assert '--profile-base' in cmd
    assert str(tmp_ns / 'browser-profiles' / 'P1') in cmd
