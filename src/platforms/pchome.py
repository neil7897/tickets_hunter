#!/usr/bin/env python3
#encoding=utf-8
"""platforms/pchome.py -- PChome 24h 購物 (24h.pchome.com.tw)"""

import asyncio
import random

import util
from nodriver_common import (
    check_and_handle_pause,
    evaluate_with_pause_check,
    play_sound_while_ordering,
    send_discord_notification,
    send_telegram_notification,
)

__all__ = [
    "nodriver_pchome_main",
]

_state = {
    "signed_in": False,
    "purchase_done": False,
    "last_button_text": None,
    "clicked": False,
}


async def _is_login_page(tab):
    result = await evaluate_with_pause_check(tab, """
        (function() {
            var url = window.location.href;
            return url.includes('ecvip.pchome.com.tw/login') ||
                   url.includes('member.pchome.com.tw') ||
                   document.querySelector('#loginId') !== null ||
                   document.querySelector('input[name="loginId"]') !== null;
        })()
    """)
    return bool(result)


async def _do_login(tab, config_dict):
    debug = util.create_debug_logger(config_dict)
    account = config_dict.get("accounts", {}).get("pchome_account", "")
    password = config_dict.get("accounts", {}).get("pchome_password", "")
    if not account or not password:
        debug.log("[PCHOME] 未設定帳號密碼，請手動登入")
        return

    debug.log(f"[PCHOME] 自動登入: {account}")
    await asyncio.sleep(random.uniform(1.0, 1.5))

    # 填帳號
    filled = await evaluate_with_pause_check(tab, f"""
        (function() {{
            var id = document.querySelector('#loginId, input[name="loginId"], input[type="email"], input[type="text"]');
            if (id) {{
                id.focus();
                id.value = {repr(account)};
                id.dispatchEvent(new Event('input', {{bubbles:true}}));
                id.dispatchEvent(new Event('change', {{bubbles:true}}));
                return true;
            }}
            return false;
        }})()
    """)
    debug.log(f"[PCHOME] 帳號填入: {filled}")
    await asyncio.sleep(random.uniform(0.5, 0.8))

    # 填密碼
    await evaluate_with_pause_check(tab, f"""
        (function() {{
            var pw = document.querySelector('#loginPwd, input[name="loginPwd"], input[type="password"]');
            if (pw) {{
                pw.focus();
                pw.value = {repr(password)};
                pw.dispatchEvent(new Event('input', {{bubbles:true}}));
                pw.dispatchEvent(new Event('change', {{bubbles:true}}));
            }}
        }})()
    """)
    await asyncio.sleep(random.uniform(0.5, 0.8))

    # 點登入按鈕
    await evaluate_with_pause_check(tab, """
        (function() {
            var btn = document.querySelector('#loginSubmit, button[type="submit"]') ||
                      Array.from(document.querySelectorAll('button, input[type="submit"]'))
                          .find(b => (b.textContent || b.value || '').includes('登入'));
            if (btn) { btn.click(); return true; }
            return false;
        })()
    """)
    debug.log("[PCHOME] 已送出登入")


async def _get_buy_button(tab):
    return await evaluate_with_pause_check(tab, """
        (function() {
            var selectors = [
                '#buy-btn',
                '.buy-btn',
                'button[id*="buy"]',
                'a[id*="buy"]',
                '#btn-buy',
                '.btn-buy',
                'button[class*="buy"]',
            ];
            for (var s of selectors) {
                var el = document.querySelector(s);
                if (el) {
                    return {
                        found: true,
                        disabled: el.disabled || el.classList.contains('disabled') ||
                                  el.classList.contains('no-stock') || el.textContent.trim().includes('缺貨'),
                        text: el.textContent.trim()
                    };
                }
            }
            var allBtns = Array.from(document.querySelectorAll('button, a, input[type="button"]'));
            var buyBtn = allBtns.find(b =>
                (b.textContent || b.value || '').includes('立即購買') ||
                (b.textContent || b.value || '').includes('加入購物車')
            );
            if (buyBtn) {
                return {
                    found: true,
                    disabled: buyBtn.disabled || buyBtn.classList.contains('disabled') || buyBtn.classList.contains('no-stock'),
                    text: (buyBtn.textContent || buyBtn.value || '').trim()
                };
            }
            return { found: false, disabled: true, text: '' };
        })()
    """)


async def _click_buy(tab, config_dict):
    debug = util.create_debug_logger(config_dict)
    clicked = await evaluate_with_pause_check(tab, """
        (function() {
            function fireClick(el) {
                el.click();
                el.dispatchEvent(new MouseEvent('mousedown', {bubbles:true}));
                el.dispatchEvent(new MouseEvent('mouseup', {bubbles:true}));
                el.dispatchEvent(new MouseEvent('click', {bubbles:true}));
            }
            var selectors = ['#buy-btn', '.buy-btn', '#btn-buy', '.btn-buy', 'button[class*="buy"]'];
            for (var s of selectors) {
                var el = document.querySelector(s);
                if (el && !el.disabled && !el.classList.contains('disabled') && !el.classList.contains('no-stock')) {
                    fireClick(el);
                    return el.textContent.trim();
                }
            }
            var btn = Array.from(document.querySelectorAll('button, a')).find(b =>
                ((b.textContent || '').includes('立即購買') || (b.textContent || '').includes('加入購物車')) &&
                !b.disabled && !b.classList.contains('disabled')
            );
            if (btn) { fireClick(btn); return btn.textContent.trim(); }
            return null;
        })()
    """)
    if clicked:
        debug.log(f"[PCHOME] 已點擊: {clicked}")
        play_sound_while_ordering(config_dict)
        send_discord_notification(config_dict, "ticket", "PChome")
        send_telegram_notification(config_dict, "ticket", "PChome")
        return True
    return False


async def nodriver_pchome_main(tab, url, config_dict):
    debug = util.create_debug_logger(config_dict)

    if _state["purchase_done"]:
        return

    if await check_and_handle_pause(config_dict):
        return

    if await _is_login_page(tab):
        if not _state["signed_in"]:
            await _do_login(tab, config_dict)
            _state["signed_in"] = True
        return

    # 訂單完成頁
    if '/checkout/result' in url or '/order/complete' in url or 'orderComplete' in url:
        if not _state["purchase_done"]:
            debug.log("[PCHOME] 訂單完成！")
            play_sound_while_ordering(config_dict)
            _state["purchase_done"] = True
        return

    # 已點擊，導向購物車等待結帳
    if _state["clicked"] and '/prod/' in url:
        await asyncio.sleep(2.0)
        await tab.get("https://24h.pchome.com.tw/cart/v3/index.htm")
        return

    # 商品頁
    if '/prod/' in url or '/DCPC' in url or 'goodsDetail' in url:
        btn = await _get_buy_button(tab)
        if btn and btn.get("found"):
            text = btn.get("text", "")
            disabled = btn.get("disabled", True)
            if text != _state["last_button_text"]:
                debug.log(f"[PCHOME] 按鈕: {text} (disabled={disabled})")
                _state["last_button_text"] = text
            if not disabled and not _state["clicked"]:
                success = await _click_buy(tab, config_dict)
                if success:
                    _state["clicked"] = True
                await asyncio.sleep(random.uniform(1.0, 1.5))
