import ipaddress
import re
import random


def replace_ip(text):
    '''
    replace all ip addresses with random ip addresses from the list of unassigned ip_address
    '''
    random_ips = ["22.214.171.124",
                  "126.96.36.199",
                  "188.8.131.52",
                  "184.108.40.206",
                  "220.127.116.11",
                  "18.104.22.168"]
    ip = re.compile(r"(?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)")
    
    def validator(match):
        ip_address = match.group()
        try:
            if ipaddress.ip_address(ip_address).is_private:
                return ip_address
            else:
                return random.choice(random_ips)
        except ValueError:  # cases: '52.0.55.019'
            return ip_address
    
    replaced_text = ip.sub(validator, text)

    return replaced_text

def replace_email(text):
    '''
    replace all emails with random emails from the list of unassigned emails
    '''
    random_emails = ["email@example.com",
                     "firstname.lastname@example.com"]
    email = re.compile(r"\b[A-Za-z0-9!#$%&'*+/=?^_`{|}~-]+(?:\.[A-Za-z0-9!#$%&'*+/=?^_`{|}~-]+)*@(?:(?:[A-Za-z0-9](?:["
            r"A-Za-z0-9-]*[A-Za-z0-9])?\.)+[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?|\[(?:(?:25[0-5]|2[0-4][0-9]|["
            r"01]?[0-9][0-9]?)\.){3}(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?|[A-Za-z0-9-]*[A-Za-z0-9]:)])")
    replaced_text = email.sub(lambda x: random.choice(random_emails), text)
    return replaced_text

if __name__ == "__main__":
    text = "My ip address is 221.243.123.11 and my email is abc.a234@gmail.com. My private ip is 192.168.1.1"
    text = replace_email(replace_ip(text))
    print(text)