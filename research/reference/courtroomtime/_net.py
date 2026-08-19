import socket, urllib.request, time
for i in range(3):
    try:
        print("dns", socket.gethostbyname("www.youtube.com"))
        break
    except Exception as e:
        print("dnsfail", e); time.sleep(2)
try:
    r = urllib.request.urlopen("https://i.ytimg.com/vi/dQw4w9WgXcQ/hqdefault.jpg", timeout=20)
    print("ytimg", r.status, len(r.read()))
except Exception as e:
    print("ytimg fail", e)
