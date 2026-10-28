"""Independent fixed composite profiles. A configured profile is not admitted."""
import json,hashlib
from core301.paths import PROJECT_ROOT
from core301.runtime.v2.errors import V2Error
VERSION='301.v2_1.composite.runtime.1'
CONFIG=PROJECT_ROOT/'config/v2_1_battle_composite_patterns.yaml'
CONFIG_SHA256='cd339d0748b8016d7aad52580562d462807ea56504dd85c1f0ce4703b1d34bf1'
def patterns():
 if hashlib.sha256(CONFIG.read_bytes()).hexdigest()!=CONFIG_SHA256:raise V2Error('PROFILE_TAMPERED','Fixed composite configuration changed')
 return json.loads(CONFIG.read_text())['patterns']
def lookup(pattern_id):
 for index,p in enumerate(patterns()):
  if p['pattern_id']==pattern_id:return index,p
 raise V2Error('PATTERN_NOT_OPEN','Unknown composite profile')
