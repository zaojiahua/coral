import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication
from email.utils import formataddr


class EmailManager():

    mail_host = 'smtp.qq.com'
    mail_user = '2273088461@qq.com'
    mail_pass = 'mnxqcyxfhnxaeaed'
    mail_sender = '2273088461@qq.com'

    @staticmethod
    def send_email(receivers, title, content, enclosure=None):
        if len(receivers) == 0:
            return
        msg = MIMEMultipart()
        msg['From'] = formataddr(['Coral机器人', EmailManager.mail_sender])
        msg['To'] = ','.join(receivers)
        msg['Subject'] = title

        # 邮件正文
        msg.attach(MIMEText(content, 'plain', 'utf-8'))

        if enclosure:
            for filepath in enclosure:
                with open(filepath, 'rb') as f:
                    # 设置附件的MIME和文件名，这里是png类型:
                    mime = MIMEApplication(f.read())
                    # 加上必要的头信息
                    mime.add_header('Content-Disposition', 'attachment', filename=filepath[filepath.rfind(os.path.sep) + 1:])
                    # 添加到MIMEMultipart:
                    msg.attach(mime)

        # 登录并发送邮件
        try:
            email_client = smtplib.SMTP()
            # 连接到服务器
            email_client.connect(EmailManager.mail_host, 25)
            # 登录到服务器
            email_client.login(EmailManager.mail_user, EmailManager.mail_pass)
            email_client.sendmail(EmailManager.mail_sender, receivers, msg.as_string())
            # 退出
            email_client.quit()
            return 0
        except smtplib.SMTPException as e:
            print('error', e)
            return 1