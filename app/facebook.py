"""Post the finished video to the Facebook Page and drop the affiliate link in the first comment."""
import time

import requests

from . import config


def post_video(path, caption):
    url = f"https://graph-video.facebook.com/{config.FB_GRAPH_VERSION}/{config.FB_PAGE_ID}/videos"
    with open(path, "rb") as f:
        r = requests.post(url, data={"access_token": config.FB_PAGE_TOKEN, "description": caption},
                          files={"source": f}, timeout=600)
    j = r.json()
    if "id" not in j:
        raise RuntimeError(f"Facebook đăng video lỗi: {j}")
    return j["id"]


def comment(object_id, message):
    url = f"https://graph.facebook.com/{config.FB_GRAPH_VERSION}/{object_id}/comments"
    last = None
    for _ in range(6):   # the video may need a moment to finish processing before comments are accepted
        r = requests.post(url, data={"access_token": config.FB_PAGE_TOKEN, "message": message}, timeout=60)
        j = r.json()
        if "id" in j:
            return j["id"]
        last = j
        time.sleep(20)
    raise RuntimeError(f"Facebook comment lỗi: {last}")


def comment_text(links):
    """links: newline-separated, each 'url' or 'Tên: url' (max 3)."""
    lines = [l.strip() for l in (links or "").splitlines() if l.strip()][:3]
    if not lines:
        return None
    if len(lines) == 1 and lines[0].startswith("http"):
        return config.FB_COMMENT_TEMPLATE.format(link=lines[0])
    return config.FB_COMMENT_MULTI_HEADER + "\n" + "\n".join(f"• {l}" for l in lines)


def publish(path, caption, links):
    vid = post_video(path, caption)
    text = comment_text(links)
    cid = comment(vid, text) if text else None
    return vid, cid, f"https://www.facebook.com/{vid}"
