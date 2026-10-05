import hashlib, hmac, os

SECRET = (os.getenv('MINIAPP_SECRET') or os.getenv('BOT_TOKEN') or 'dev-secret-change-me').encode('utf-8')

def sign(chat_id:int, user_id:int, mode:str) -> str:
    msg=f'{chat_id}:{user_id}:{mode}'.encode()
    return hmac.new(SECRET,msg,hashlib.sha256).hexdigest()[:32]

def verify(chat_id:int,user_id:int,mode:str,token:str) -> bool:
    return hmac.compare_digest(sign(chat_id,user_id,mode),token or '')
