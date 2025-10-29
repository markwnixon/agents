import paramiko

scac = 'oslm'
ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect('172.233.199.180', username='mark', key_filename='/home/mark/.ssh/id_rsa')

stdin, stdout, stderr = ssh.exec_command(f'getpin2.sh {scac} &')  # & makes it non-blocking
exit_status = stdout.channel.recv_exit_status()  # Waits for command to finish
output = stdout.read().decode()
errors = stderr.read().decode()
ssh.close()

if exit_status == 0:
    print("✅ Success:", output)
    #return {"status": "success", "output": output}
else:
    print("❌ Error:", errors)
    #return {"status": "error", "error": errors}