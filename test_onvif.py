from onvif import ONVIFCamera

IP = "192.168.1.203"
PORT = 8080  # a volte 8899 o 8000, dipende dalla camera
USER = "admin"
PASS = "123456"

camera = ONVIFCamera(IP, PORT, USER, PASS)

media = camera.create_media_service()

profiles = media.GetProfiles()

print("\n=== PROFILI CAMERA ===\n")

for p in profiles:
    print("Profile:", p.Name)

    stream_uri = media.GetStreamUri({
        'StreamSetup': {
            'Stream': 'RTP-Unicast',
            'Transport': {'Protocol': 'RTSP'}
        },
        'ProfileToken': p.token
    })

    print("RTSP URL:")
    print(stream_uri.Uri)
    print("-" * 50)