"""Start the hosted gateway from its private configuration; never use the owner's login."""
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
config_path = Path(os.environ.get('MOTIONCLONE_GATEWAY_CONFIG', ROOT / 'data/.hosted/settings.json'))
config = json.loads(config_path.read_text(encoding='utf-8'))
os.environ['MOTIONCLONE_GATEWAY_SECRET'] = config['secret']
os.environ['MOTIONCLONE_HOSTED_DATA'] = str(config_path.parent / 'users')
os.environ['MOTIONCLONE_MAX_USERS'] = str(config.get('max_users', 3))

if __name__ == '__main__':
    import uvicorn
    from app.hosted_gateway import configured_gateway
    uvicorn.run(configured_gateway(), host='127.0.0.1', port=config.get('port', 4320), access_log=False)
