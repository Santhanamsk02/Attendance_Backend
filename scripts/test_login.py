import urllib.request
import urllib.error

req = urllib.request.Request(
    'https://attendance-backend-37wj.onrender.com/api/v1/auth/login', 
    data=b'username=superadmin%40pec.edu&password=admin', 
    headers={'Content-Type': 'application/x-www-form-urlencoded'}
)
try:
    urllib.request.urlopen(req)
    print("Success!")
except urllib.error.HTTPError as e:
    print("Error:", e.code)
    print("Body:", e.read().decode())
