
1. [Register on Arkham Exchange](https://auth.arkm.com/register?ref=hodlyouwill) and complete KYC. Wait till KYC is successful.

1.1 After successful KYC, enter Akrham, activate 2FA and get API key. Save API key and keep it private.

2. Top up Arkham Exchange balance, with $150. Buy for $40 ARKM (for future fees).

3. Create AWS account and create free EC2 instance (with nameofyoufile.pem).

3.1 Rename apikey.env.example to apikey.env. Add your keys to .env file and move it to YOUR EC2 via SCP in terminal.
```
scp -i nameofyoufile.pem trade.py ec2-user@youripaddress:~
```
3.2 Move .py file and to EC2:
```
scp -i nameofyoufile.pem trade.py ec2-user@youripaddress:~
```
3.3 Connect to AWS EC2 instance using terminal:
```
ssh -i nameofyoufile.pem ec2-user@youripaddress
```
3.4 Run this line, it will install all needed for python script.
```
sudo yum install -y python3 python3-pip && pip install python-dotenv && pip3 install pynacl && pip install aiohttp && pip install uvloop
```
4. on your EC2 run python script:
```
python3 trade.py
```
If all successful, you will see calculated spreads and traded volume.

P.S.
Calculation for getting 500 Arkham Points:

you get $210 in fee rebate
210 / 0.05% = 420 000
80 000 * 0.0375% = 30

with spreads on BTC/USDT perp as low as 0.01 we can hardly get more than total slippage higher than $4 for 500 000 volume.

So for $35 spent we get 500 Akrham Points (500 ARKM tokens after Season 2 ends) (+ base reward is likely).

Spend $35, get at least $235.

P.P.S.
If you have more funds, I would keep on making volume as with more volume you get +50% to points and lower fees. You can make your calculations yourself
on Akrham Exchange Website.

Info valid fro 16 June 2025.
