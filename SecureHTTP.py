# -*- coding: utf-8 -*-
"""
    Python-SecureHTTP
    ~~~~~~~~~~~~~~~~~

    关于通信过程加密算法的说明：

    1. AES加解密::

        模式：CBC
        密钥长度：128位
        密钥key和初始偏移向量iv一致
        补码方式：PKCS5Padding
        加密结果编码方式：十六进制

    2. RSA加解密::

        算法：RSA
        填充：RSA_PKCS1_PADDING
        密钥格式：符合PKCS#1规范，密钥对采用PEM形式

    3. 签名::

        对请求参数或数据添加公共参数后排序再使用MD5签名

    :copyright: (c) 2019 by staugur.
    :license: MIT, see LICENSE for more details.
"""

import re
import sys
import rsa
import json
import time
import copy
import base64
import hashlib
from operator import mod
try:
    from Cryptodome import Random
    from Cryptodome.Cipher import AES
    from Cryptodome.PublicKey import RSA
except ImportError:
    from Crypto import Random
    from Crypto.Cipher import AES
    from Crypto.PublicKey import RSA

__version__ = "0.2.4"
__author__ = "staugur <staugur@saintic.com>"
__all__ = ["RSAEncrypt", "RSADecrypt", "AESEncrypt", "AESDecrypt", "EncryptedCommunicationClient", "EncryptedCommunicationServer", "generate_rsa_keys"]

PY2 = sys.version_info[0] == 2
if PY2:
    from urllib import quote
    string_types = (str, unicode)
    public_key_prefix = u"-----BEGIN RSA PUBLIC KEY-----"
else:
    from urllib.request import quote
    string_types = (str,)
    public_key_prefix = b"-----BEGIN RSA PUBLIC KEY-----"


class SecureHTTPException(Exception):
    pass


class SignError(SecureHTTPException):
    """签名错误：加签异常、验签不匹配等"""
    pass


class AESError(SecureHTTPException):
    """AES加密、解密时参数错误"""
    pass


def generate_rsa_keys(length=1024, incall=False):
    """生成RSA所需的公钥和私钥，公钥格式pkcs8，私钥格式pkcs1。

    :param length: int: 指定密钥长度，默认1024，需要更强加密可设置为2048

    :param incall: bool: 是否内部调用，默认False表示提供给脚本调用直接打印密钥，True不打印密钥改为return返回

    :returns: tuple(public_key, private_key)
    """
    if not incall:
        args = sys.argv[1:]
        if args:
            try:
                length = int(args[0])
            except:
                pass
        print("\033[1;33mGenerating RSA private key, %s bit long modulus.\n\033[0m" % length)
        startTime = time.time()
    # 开始生成
    random_generator = Random.new().read
    key = RSA.generate(length, random_generator)
    pub_key = key.publickey()
    public_key = pub_key.exportKey("PEM", pkcs=8)
    private_key = key.exportKey("PEM", pkcs=1)
    # 生成完毕
    if not incall:
        print("\033[1;32mSuccessfully generated, with %0.2f seconds.\nPlease save the key pair and don't reveal the private key!\n\033[0m" % float(time.time() - startTime))
        print("\033[1;31mRSA PublicKey for PKCS#8:\033[0m\n%s" % public_key.decode('utf-8'))
        print("\n\033[1;31mRSA PrivateKey for PKCS#1:\033[0m\n%s" % private_key.decode('utf-8'))
    else:
        return (public_key, private_key)


def RSAEncrypt(pubkey, plaintext):
    """RSA公钥加密

    :param pubkey: str,bytes: pkcs1或pkcs8格式公钥

    :param plaintext: str: 准备加密的文本消息

    :returns: str,unicode: base64编码的字符串
    """
    if pubkey and pubkey.startswith(public_key_prefix):
        pubkey = rsa.PublicKey.load_pkcs1(pubkey)
    else:
        # load_pkcs1_openssl_pem可以加载openssl生成的pkcs1公钥(实为pkcs8格式)
        pubkey = rsa.PublicKey.load_pkcs1_openssl_pem(pubkey)
    ciphertext = rsa.encrypt(plaintext.encode('utf-8'), pubkey)
    return base64.b64encode(ciphertext).decode('utf-8')


def RSADecrypt(privkey, ciphertext):
    """RSA私钥解密

    :param privkey: str,bytes: pkcs1格式私钥

    :param ciphertext: str: 已加密的消息

    :returns: 消息原文
    """
    privkey = rsa.PrivateKey.load_pkcs1(privkey)
    plaintext = rsa.decrypt(base64.b64decode(ciphertext), privkey)
    return plaintext.decode('utf-8')


def AESEncrypt(key, plaintext):
    """AES加密
    :param key: str: 16位的密钥串

    :param plaintext: str: 将加密的明文消息

    :raises: AESError

    :returns: str,unicode: 加密后的十六进制
    """
    if key and isinstance(key, string_types) and mod(len(key), 16) == 0 and plaintext and isinstance(plaintext, string_types):
        def PADDING(s): return s + (AES.block_size - len(s) % AES.block_size) * chr(AES.block_size - len(s) % AES.block_size)
        key = key.encode("utf-8")
        generator = AES.new(key, AES.MODE_CBC, key[:AES.block_size])
        plaintext = PADDING(plaintext)
        ciphertext = generator.encrypt(plaintext.encode('utf-8'))
        crypted_str = base64.b64encode(ciphertext)
        return crypted_str.decode('utf-8')
    else:
        raise AESError("Parameter error: key or ciphertext type is not valid, or key length is not valid")


def AESDecrypt(key, ciphertext):
    """AES解密
    :param key: str: 16位的密钥串

    :param ciphertext: str,unicode: 已加密的十六进制数据密文

    :raises: AESError

    :returns: str,bool(False): 返回False时说明解密失败，成功则返回数据
    """
    if key and isinstance(key, string_types) and mod(len(key), 16) == 0 and ciphertext and isinstance(ciphertext, string_types):
        key = key.encode("utf-8")
        generator = AES.new(key, AES.MODE_CBC, key[:AES.block_size])
        ciphertext += (len(ciphertext) % 4) * '='
        decrpyt_bytes = base64.b64decode(ciphertext)
        msg = generator.decrypt(decrpyt_bytes)
        # 去除解码后的非法字符
        try:
            result = re.compile('[\\x00-\\x08\\x0b-\\x0c\\x0e-\\x1f\n\r\t]').sub('', msg.decode())
        except Exception:
            return False
        else:
            return result
    else:
        raise AESError("Parameter error: key or ciphertext type is not valid, or key length is not valid")


class EncryptedCommunicationMix(object):
    """加密传输通信基类。

    此类封装加密通信过程中所需函数，包括RSA、AES、MD5等，加密传输整个流程是::

        客户端上传数据加密 ==> 服务端获取数据解密 ==> 服务端返回数据加密 ==> 客户端获取数据解密

    NO.1 客户端上传数据加密流程::

        1. 客户端随机产生一个16位的字符串，用以之后AES加密的秘钥，AESKey。
        2. 使用RSA对AESKey进行公钥加密，RSAKey。
        3. 参数加签，规则是：对所有请求或提交的字典参数按key做升序排列并用"参数名=参数值&"形式连接。
        4. 将明文的要上传的数据包(字典/Map)转为Json字符串，使用AESKey加密，得到JsonAESEncryptedData。
        5. 封装为{key : RSAKey, value : JsonAESEncryptedData}的字典上传服务器，服务器只需要通过key和value，然后解析，获取数据即可。

    NO.2 服务端获取数据解密流程::

        1. 获取到RSAKey后用服务器私钥解密，获取到AESKey
        2. 获取到JsonAESEncriptedData，使用AESKey解密，得到明文的客户端上传上来的数据。
        3. 验签
        4. 返回明文数据

    NO.3 服务端返回数据加密流程::

        1. 将要返回给客户端的数据(字典/Map)进行加签并将签名附属到数据中
        2. 上一步得到的数据转成Json字符串，用AESKey加密处理，记为AESEncryptedResponseData
        3. 封装数据{data : AESEncryptedResponseData}的形式返回给客户端

    NO.4 客户端获取数据解密流程::

        1. 客户端获取到数据后通过key为data得到服务器返回的已经加密的数据AESEncryptedResponseData
        2. 对AESEncryptedResponseData使用AESKey进行解密，得到明文服务器返回的数据。
    """

    def get_current_timestamp(self):
        """ UTC时间 """
        return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    def md5(self, message):
        """MD5签名

        :params message: str,unicode,bytes:

        :returns: str: Signed message
        """
        if not PY2 and isinstance(message, str):
            message = message.encode("utf-8")
        return hashlib.md5(message).hexdigest()

    def genAesKey(self):
        """生成AES密钥，长度32

        :returns: str
        """
        return self.md5(Random.new().read(AES.block_size))

    def conversionComma(self, comma_str):
        """将字符串comma_str使用正则以逗号分隔

        :param comma_str: str: 要分隔的字符串，以英文逗号分隔

        :return: list
        """
        if comma_str and isinstance(comma_str, string_types):
            comma_pat = re.compile(r"\s*,\s*")
            return [i for i in comma_pat.split(comma_str) if i]
        else:
            return tuple()

    def sign(self, parameters, meta={}):
        """ 参数签名，目前版本请勿嵌套无序数据类型（如嵌套dict、嵌套list中嵌套dict），否则可能造成签名失败！

        :param parameters: dict: 请求参数或提交的数据

        :param meta: dict: 公共元数据，参与排序加签

        :raises: TypeError

        :returns: md5 message(str) or None
        """
        if isinstance(parameters, dict) and isinstance(meta, dict):
            signIndex = meta.get("SignatureIndex", None)
            # 重新定义要加签的dict
            if signIndex is False:
                return
            elif signIndex and isinstance(signIndex, string_types):
                signIndex = self.conversionComma(signIndex)
                data = dict()
                for k in signIndex:
                    data[k] = parameters[k]
            else:
                data = copy.deepcopy(parameters)
            # 追加公共参数
            for k, v in meta.items():
                data[k] = v
            # NO.1 参数排序
            _my_sorted = sorted(data.items(), key=lambda data: data[0])
            # NO.2 排序后拼接字符串
            canonicalizedQueryString = ''
            for (k, v) in _my_sorted:
                canonicalizedQueryString += '%s=%s&' %(self._percent_encode(k), self._percent_encode(v))
            # NO.3 加密返回签名: Signature
            return self.md5(canonicalizedQueryString)
        else:
            raise TypeError("Invalid sign parameters or meta")

    def _percent_encode(self, encodeStr):
        try:
            encodeStr = json.dumps(encodeStr, sort_keys=True)
        except:
            raise
        if isinstance(encodeStr, bytes):
            encodeStr = encodeStr.decode(sys.stdin.encoding or 'utf-8')
        res = quote(encodeStr.encode('utf-8'), '')
        res = res.replace('+', '%20')
        res = res.replace('*', '%2A')
        res = res.replace('%7E', '~')
        return res


class EncryptedCommunicationClient(EncryptedCommunicationMix):
    """客户端：主要是公钥加密"""

    def __init__(self, PublicKey):
        """初始化客户端请求类

        :param PublicKey: str: RSA的pkcs1或pkcs8格式公钥
        """
        self.AESKey = self.genAesKey()
        self.PublicKey = PublicKey

    def clientEncrypt(self, post, signIndex=None):
        """客户端发起加密请求通信 for NO.1

        :param post: dict: 请求的数据

        :param signIndex: str: 参与排序加签的键名，False表示不签名，None时表示加签post中所有数据，非空时请用逗号分隔键名(字符串)

        :returns: dict: {key=RSAKey, value=加密数据}
        """
        if not (post and isinstance(post, dict)):
            raise TypeError("Invalid post data")
        # 深拷贝post
        postData = copy.deepcopy(post)
        # 使用RSA公钥加密AES密钥获取RSA密文作为密钥
        RSAKey = RSAEncrypt(self.PublicKey, self.AESKey)
        # 定义元数据
        metaData = dict(Timestamp=self.get_current_timestamp(), SignatureVersion="v1", SignatureMethod="MD5", SignatureIndex=signIndex)
        # 对请求数据签名
        metaData.update(Signature=self.sign(postData, metaData))
        # 对请求数据填充元信息
        postData.update(__meta__=metaData)
        #  使用AES加密请求数据
        JsonAESEncryptedData = AESEncrypt(self.AESKey, json.dumps(postData, separators=(',', ':')))
        return dict(key=RSAKey, value=JsonAESEncryptedData)

    def clientDecrypt(self, encryptedRespData):
        """客户端获取服务端返回的加密数据并解密 for NO.4

        :param encryptedRespData: dict: 服务端返回的加密数据，其格式应该是 {data: AES加密数据}

        :raises: TypeError,SignError

        :returns: 解密验签成功后，返回服务端的消息原文
        """
        if encryptedRespData and isinstance(encryptedRespData, dict) and \
                "data" in encryptedRespData:
            JsonAESEncryptedData = encryptedRespData["data"]
            respData = json.loads(AESDecrypt(self.AESKey, JsonAESEncryptedData))
            metaData = respData.pop("__meta__")
            Signature = metaData.pop("Signature")
            SignData = self.sign(respData, metaData)
            if Signature == SignData:
                return respData
            else:
                raise SignError("Signature verification failed")
        else:
            raise TypeError("Invalid encrypted resp data")


class EncryptedCommunicationServer(EncryptedCommunicationMix):
    """服务端：主要是私钥解密"""

    def __init__(self, PrivateKey):
        """初始化服务端响应类

        :param PrivateKey: str: pkcs1格式私钥
        """
        self.PrivateKey = PrivateKey
        # AESKey是服务端解密时解码的AESKey，即客户端加密时自主生成的AES密钥
        self.AESKey = None

    def serverDecrypt(self, encryptedPostData):
        """服务端获取请求数据并解密 for NO.2

        :param encryptedPostData: dict: 请求的加密数据

        :raises: TypeError,SignError

        :returns: 解密后的请求数据原文
        """
        if encryptedPostData and isinstance(encryptedPostData, dict) and \
            "key" in encryptedPostData and \
                "value" in encryptedPostData:
            RSAKey = encryptedPostData["key"]
            self.AESKey = RSADecrypt(self.PrivateKey, RSAKey)
            JsonAESEncryptedData = encryptedPostData["value"]
            postData = json.loads(AESDecrypt(self.AESKey, JsonAESEncryptedData))
            metaData = postData.pop("__meta__")
            Signature = metaData.pop("Signature")
            SignData = self.sign(postData, metaData)
            if Signature == SignData:
                return postData
            else:
                raise SignError("Signature verification failed")
        else:
            raise TypeError("Invalid encrypted post data")

    def serverEncrypt(self, resp, signIndex=None):
        """服务端返回加密数据 for NO.3

        :param resp: dict: 服务端返回的数据，目前仅支持dict

        :param signIndex: tuple,list: 参与排序加签的键名，False表示不签名，None时表示加签resp中所有数据，非空时请用逗号分隔键名(字符串)

        :raises: TypeError,ValueError

        :returns: dict: 返回dict，格式是 {data: AES加密数据}
        """
        if self.AESKey:
            if resp and isinstance(resp, dict):
                respData = copy.deepcopy(resp)
                metaData = dict(Timestamp=self.get_current_timestamp(), SignatureVersion="v1", SignatureMethod="MD5", SignatureIndex=signIndex)
                metaData.update(Signature=self.sign(respData, metaData))
                respData.update(__meta__=metaData)
                JsonAESEncryptedData = AESEncrypt(self.AESKey, json.dumps(respData, separators=(',', ':')))
                return dict(data=JsonAESEncryptedData)
            else:
                raise TypeError("Invalid resp data")
        else:
            raise ValueError("Invalid AESKey")
