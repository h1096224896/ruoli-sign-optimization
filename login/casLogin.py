import re
import requests
from bs4 import BeautifulSoup
from urllib3.exceptions import InsecureRequestWarning
from login.Utils import Utils
from liteTools import Image

requests.packages.urllib3.disable_warnings(InsecureRequestWarning)


class casLogin:
    # 初始化cas登陆模块
    def __init__(self, username, password, login_url, host, session):
        self.username = username
        self.password = password
        self.login_url = login_url
        self.host = host
        self.session: requests.Session = session
        self.formType = ""

    # 判断是否需要验证码
    def getNeedCaptchaUrl(self):
        if self.formType == "casLoginForm":
            url = (
                self.host + "authserver/needCaptcha.html" + "?username=" + self.username
            )
            flag = self.session.get(url, verify=False).text
            if re.search("false", flag, re.I):
                return False
            else:
                return True
        else:
            url = self.host + "authserver/checkNeedCaptcha.htl"
            flag = self.session.get(
                url, params={"username": self.username}, verify=False
            ).json()
            return flag["isNeed"]

    def solve_captcha(self, params: dict):
        """
        解决验证码问题
        :param params: 正在填写的登录参数
        """
        # 滑块验证
        if self.captcha_type == "slider":
            get_captcha_url = self.host + "authserver/common/openSliderCaptcha.htl"
            verify_captcha_url = self.host + "authserver/common/verifySliderCaptcha.htl"
            captcha_data = self.session.get(get_captcha_url).json()
            solution = Image.solve_slide(
                captcha_data["smallImage"], captcha_data["bigImage"]
            )
            verify_data = {
                "canvasLength": 280,
                "moveLength": int(280 * solution["slide"] / solution["canvas"]),
            }
            self.session.post(verify_captcha_url, data=verify_data)
            return

        # 验证码验证
        if self.formType == "casLoginForm":
            imgUrl = self.host + "authserver/captcha.html"
            params["captchaResponse"] = Utils.getCodeFromImg(self.session, imgUrl)
        else:
            imgUrl = self.host + "authserver/getCaptcha.htl"
            params["captcha"] = Utils.getCodeFromImg(self.session, imgUrl)

    def login(self):
        html = self.session.get(self.login_url, verify=False).text
        if re.findall('<form[^<]*id="casLoginForm"[^>]*>', html, re.I):
            self.formType = "casLoginForm"
        elif re.findall('<form[^<]*id="loginFromId"[^>]*>', html, re.I):
            self.formType = "loginFromId"
        elif re.findall('<form[^<]*id="fm1"[^>]*>', html, re.I):
            self.formType = "fm1"
        # 在html中寻找所有form元素(备注: form几乎不会嵌套form)
        formElementList = re.findall(r"<form[\s\S]*?</form>", html)
        # 初始化需要的参数
        params = {}
        salt = ""
        # 寻找包含"password"的form元素
        for form in formElementList:
            if re.findall("password", form, re.I):
                # 在input元素中，查找salt和一些需要提交参数

                inputElementList = re.findall(r"<input[\s\S]*?>", form)
                for inputElement in inputElementList:
                    # 查找salt
                    if re.findall(r"EncryptSalt", inputElement, re.I):
                        salt = re.findall(r'value="(.*?)"', inputElement)[0]
                    # 排除type为非文本类型input元素
                    if re.findall(
                        r'type="(?:button|checkbox|file|image|radio|reset|submit)"',
                        inputElement,
                    ):
                        continue
                    # 查找需要提交的数据的键
                    if re.findall(r"name=", inputElement):
                        key = re.findall(r'name="(.*?)"', inputElement)[0]
                    else:
                        continue
                    # 查找需要提交的数据的值
                    if re.findall(r"value=", inputElement):
                        value = re.findall(r'value="(.*?)"', inputElement)[0]
                    else:
                        value = ""
                    # 填入即将提交的参数字典中
                    params[key] = value
        if not salt:
            """salt可能藏在script中"""
            maySalt = re.findall(r'var pwdDefaultEncryptSalt ?= ?"(.*?)"', html)
            if maySalt:
                salt = maySalt[0]
        # 将用户名填入即将提交的参数中
        params["username"] = self.username
        # 检查验证码类型
        self.captcha_type = "code"
        if re.findall("sliderCaptchaDiv", html):
            self.captcha_type = "slider"
        # 将密码填入即将提交的参数中
        if salt:
            params["password"] = Utils.encryptAES(self.password, salt)
            # 识别填写验证码
            if self.getNeedCaptchaUrl():
                self.solve_captcha(params)
        else:
            params["password"] = self.password

        # 发送数据尝试登录
        data = self.session.post(self.login_url, data=params, allow_redirects=False)
        # 如果等于302强制跳转，代表登陆成功
        if data.status_code == 302:
            jump_url = data.headers["Location"]
            self.session.headers["Server"] = "CloudWAF"
            res = self.session.get(jump_url, verify=False)
            if res.status_code == 200:
                return self.session.cookies
            else:
                res = self.session.get(
                    re.findall(r"\w{4,5}\:\/\/.*?\/", self.login_url)[0], verify=False
                )
                if res.status_code == 200 or res.status_code == 404:
                    return self.session.cookies
                else:
                    raise Exception("登录失败，请反馈BUG")
        elif data.status_code == 200:
            print(data.content)
            soup = BeautifulSoup(data.text, "lxml")
            if self.formType == "casLoginForm":
                msg = soup.select("#errorMsg")
                if len(msg) != 0:
                    msg = msg[0].get_text()
                else:
                    msg = soup.select("#msg")
                    if len(msg) != 0:
                        msg = msg[0].get_text()
                    else:
                        msg = soup.select(".authError")
                        if len(msg) != 0:
                            msg = msg[0].get_text()
            else:
                msg = soup.select("#formErrorTip2")[0].get_text()
            print("=============================================================")
            displayError = re.findall(
                r'"([^"]*[Ee]rror[^"]*)"[^>]*style="(?!display:none;)[^>]*">', data.text
            )
            print(displayError)
            error_tip = re.findall(
                r'<span .*id="showErrorTip".*>(?:[\s\S]*?)<\/span>', data.text
            )
            if error_tip:
                error_tip = error_tip.group()
                print(error_tip)
            else:
                print(data.text)
            raise Exception(msg + "\n" + str(displayError) + "\n" + str(error_tip))
        else:
            error_tip = re.search(
                r'<span .*id="showErrorTip".*>(?:[\s\S]*?)<\/span>', data.text, re.M
            )
            if error_tip:
                print(error_tip.group(0))
            else:
                print(data.text)
                error_tip = ""
            raise Exception(
                "教务系统出现了问题啦！返回状态码："
                + str(data.status_code)
                + "\n错误提示: "
                + str(error_tip)
            )
