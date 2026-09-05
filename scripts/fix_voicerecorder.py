import re

file_path = r'itds_env/frontend/src/components/VoiceRecorder.js'

with open(file_path, 'r', encoding='utf-8') as f:
    content = f.read()

# Remove all lines starting with @@ (they're malformed)
content = re.sub(r'^\s*@@.*\n', '', content, flags=re.MULTILINE)

with open(file_path, 'w', encoding='utf-8') as f:
    f.write(content)

print("File cleaned!")
