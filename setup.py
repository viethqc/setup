import os
from subprocess import Popen, PIPE
import json
import traceback
import sys
import paramiko 

from StringIO import StringIO
import paramiko 

class SshClient:
	TIMEOUT = 4

	def __init__(self, host, port, username, password, key=None, passphrase=None):
		self.username = username
		self.password = password
		self.client = paramiko.SSHClient()
		self.client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
		if key is not None:
			key = paramiko.RSAKey.from_private_key(StringIO(key), password=passphrase)
		self.client.connect(host, port, username=username, password=password, pkey=key, timeout=self.TIMEOUT)

		self.transport =  paramiko.Transport(host, port)
		self.transport.connect(username=username, password=password)
		self.sftp = paramiko.SFTPClient.from_transport(self.transport)

	def close(self):
		if self.client is not None:
			self.client.close()
			self.client = None

	def hello(self):
		print "hello"

	def put(self, src_file, dest_file):
		self.sftp.put(src_file, dest_file)

	def rmdir(self, dir):
		self.sftp.rmdir(dir)

	def mkdir(self, dir):
		self.sftp.mkdir(dir)

	def chmod(self, path, mode):
		self.sftp.chmod(path, mode)


	def execute(self, command, sudo=False):
		feed_password = False
		if sudo and self.username != "root":
			command = "sudo -S -p '' %s" % command
			feed_password = self.password is not None and len(self.password) > 0
		stdin, stdout, stderr = self.client.exec_command(command)
		if feed_password:
			stdin.write(self.password + "\n")
			stdin.flush()

		return {'out': stdout.readlines(), 
				'err': stderr.readlines(),
				'retval': stdout.channel.recv_exit_status()}

	def fuck(self, command, list_input = [], sudo=False):
		feed_password = False
		if sudo and self.username != "root":
			command = "sudo -S -p '' %s" % command
			feed_password = self.password is not None and len(self.password) > 0
		stdin, stdout, stderr = self.client.exec_command(command)
		if feed_password:
			stdin.write(self.password + "\n")
			stdin.flush()

		print stdout.readlines()
		stdin.write("dm\n")
		stdin.flush()
		print stdout.readlines()

		return {'out': stdout.readlines(), 
                'err': stderr.readlines(),
                'retval': stdout.channel.recv_exit_status()}

client = SshClient(host='192.168.1.6', port=22, username='viethq', password='a') 
ret = client.fuck('/home/viethq/setup/demo.sh', ["dm", "5"], sudo=True)
print "  ".join(ret["out"]), "  E ".join(ret["err"]), ret["retval"]
sys.exit()

#ssh = paramiko.SSHClient()
#ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
#ssh.connect("192.168.1.6", username="viethq", password="a")
#ssh_stdin, ssh_stdout, ssh_stderr = ssh.exec_command("service docker restart")
#print ssh_stdout
#sys.exit()

def read_config():
    try:
        file = open("config.json", "r")
        data = file.read()
        file.close()

	return json.loads(data)
    except:
	traceback.print_exc()
	return {}

def run_command(command):
    arr_command = command.split(" ")
    process = Popen(arr_command, stdout=PIPE, stderr=PIPE)
    stdout, stderr = process.communicate()
    process.wait()
    return stdout, stderr

print "==============================read config ======================================"
config_data = read_config()
print config_data

image_dir = config_data["image_dir"]
print "image_dir: " + image_dir


registry = config_data["registry"]
print "registry: " + registry

app_dir = config_data["app_dir"]
print "app dir: " + app_dir


master_node = {}
list_worker = []

servers = config_data["servers"]
for server in servers:
	if server["node_type"] == "master":
		master_node = server
	else:
		list_worker.append(server)


print "===============================load image and push to registry=========================="
list_image = os.listdir(image_dir)
print "image list: " + str(list_image)

for image in list_image:
    file_path = os.path.join(image_dir, image)
    out, err = run_command("docker load -i " + file_path)
    out = out.lower()
    out = out.strip()
    if out.find("loaded image") == -1:
	continue

    arr_data = out.split("loaded image: ")

    #parse old registry and image name
    image_loaded = arr_data[1].strip()
    print "image loaded: " + image_loaded
    arr_data = image_loaded.split("/")
    read_image = ""

    if len(arr_data) == 1:
        real_image = arr_data[0]
    else:
        real_image = arr_data[1]

    print "real image: " + real_image
    new_image = registry + "/" + real_image
    print "new image: " + new_image
    out, err = run_command("docker tag " + image_loaded + " " + new_image)
    print out

    out, err = run_command("docker push " + new_image)
    print out

print "==========================Install normal app======================="
for server in servers:
	print server
	client = SshClient(host=server["ip"], port=22, username=server["user"], password=server["pass"])
	ret = client.execute("mkdir setup", sudo=False)

	list_file = os.listdir(app_dir)
	for file_name in list_file:
		file_path = os.path.join(app_dir, file_name)
		dest_file = "/home/" + server["user"] + "/setup/" + file_name
		client.put(file_path, dest_file)
		client.chmod(dest_file, 777)
#	ret = client.execute("scp app_normal/* " + server["user"] + "@" + server["ip"] + ":setup", sudo=False)
#	print ret
	client.close()

sys.exit()



print "===============================Join swarm=========================="
print master_node

client = SshClient(host=master_node["ip"], port=22, username=master_node["user"], password=master_node["pass"])
ret = client.execute("docker swarm leave --force", sudo=False)
ret = client.execute('docker swarm init --advertise-addr ' + master_node["ip"] + ":2377", sudo=False)
client.close()

command_join_swarm = ""
for line in ret["out"]:
    line = line.strip()
    if line.find("docker swarm join --token") != -1:
	command_join_swarm = line
	break

print command_join_swarm
for server in list_worker:
	print "join " + server["ip"] + "to swarm"
	client = SshClient(host=server["ip"], port=22, username=server["user"], password=server["pass"])
	ret = client.execute(command_join_swarm, sudo=False)
	print ret["out"]
	client.close()

#print arr_data
#print "  ".join(ret["out"])
