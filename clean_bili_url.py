def clean_bilibili_url(url):
    # 查找第五个 '/' 的位置，并截断该位置之后的内容
    url_parts = url.split('/')
    if len(url_parts) > 5:
        clean_url = '/'.join(url_parts[:5])
    else:
        clean_url = url
    return clean_url