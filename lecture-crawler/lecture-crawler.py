import json
import re
import getpass
import base64
import requests
import time
import sys
from Crypto.PublicKey import RSA
from Crypto.Cipher import PKCS1_v1_5

class HttpRequest:
	def __init__(self):
		self._s = requests.Session()
		self._s.headers.update({
			'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/80.0.3987.132 Safari/537.36',
			'Content-Type': 'application/json; charset=utf-8'
		})

	def __del__(self):
		self._s.close()

	def getRequest(self, url):
		return self._s.get(url)
	
	def postRequest(self, url, data = {}):
		return self._s.post(url, json.dumps(data))

def log_message(error_type, message):
	print('[' + error_type + ']', message)

def get_lecture_info(syllabus_info):
	lecture_info = []
	lecture_time = {}

	# If there is no syllabus
	if syllabus_info['closeOpt'] == 'Y' or syllabus_info['summary'] == None:
		return []

	timetable_result = hr.postRequest('https://klas.kw.ac.kr/std/cps/atnlc/LectreTimeInfo.do', {
		'selectSubj': 'U' + syllabus_info['thisYear'] + syllabus_info['hakgi'] + syllabus_info['openGwamokNo'] + syllabus_info['openMajorCode'] + syllabus_info['bunbanNo'] + syllabus_info['openGrade'],
		'selectYear': syllabus_info['thisYear'],
		'selecthakgi': syllabus_info['hakgi']
	}).json()

	# Parse timetable
	for timetable_info in timetable_result:
		lecture_room_name = timetable_info['locHname']
		week_name = timetable_info['dayname1']
		class_time = []

		# If there is no lecture room
		if lecture_room_name == None:
			continue

		# If it is online lecture
		if week_name == '토':
			continue

		if timetable_info['timeNo1'] != None: class_time.append(timetable_info['timeNo1'])
		if timetable_info['timeNo2'] != None: class_time.append(timetable_info['timeNo2'])
		if timetable_info['timeNo3'] != None: class_time.append(timetable_info['timeNo3'])
		if timetable_info['timeNo4'] != None: class_time.append(timetable_info['timeNo4'])

		if lecture_room_name not in lecture_time:
			lecture_time[lecture_room_name] = {}
		
		lecture_time[lecture_room_name][week_name] = class_time

	# Make datas
	for lecture_room_name in lecture_time:
		lecture_building_name = re.compile('[^0-9A-Z]+').search(lecture_room_name).group()
		lecture_building_name = building_name_changer[lecture_building_name]
		lecture_room_number = re.compile('[0-9A-Z]+').search(lecture_room_name).group()

		lecture_info.append({
			'lectureName': syllabus_info['gwamokKname'],
			'professorName': syllabus_info['memberName'],
			'majorCode': syllabus_info['openMajorCode'],
			'lectureBuildingName': lecture_building_name,
			'lectureRoomNumber': lecture_room_number,
			'timeTable': lecture_time[lecture_room_name]
		})
	
	return lecture_info

def progress_bar(value, end_value, bar_length = 30):
	percent = value / end_value
	arrow = '-' * int(round(percent * bar_length) - 1) + '>'
	spaces = ' ' * (bar_length - len(arrow))

	sys.stdout.write('\r진행 중 ... [{0}] {1}%'.format(arrow + spaces, int(round(percent * 100))))
	sys.stdout.flush()

def main():
	# Set login datas
	login_id = input('학번을 입력해 주세요 : ')
	login_pw = getpass.getpass(prompt = '비밀번호를 입력해 주세요 : ', stream = None)
	login_datas = json.dumps({
		'loginId': login_id,
		'loginPwd': login_pw,
		'storeIdYn': 'N'
	})

	# Encrypt with RSA
	public_key = hr.postRequest('https://klas.kw.ac.kr/usr/cmn/login/LoginSecurity.do').json()['publicKey']
	rsa_key = RSA.import_key(base64.b64decode(public_key))
	cipher = PKCS1_v1_5.new(rsa_key)
	login_token = cipher.encrypt(bytes(login_datas, 'utf8'))
	login_token = base64.b64encode(login_token).decode()

	# Request login
	login_result = hr.postRequest('https://klas.kw.ac.kr/usr/cmn/login/LoginConfirm.do', {
		'loginToken': login_token,
		'redirectUrl': '',
		'redirectTabUrl': ''
	}).json()

	if len(login_result['fieldErrors']) > 0:
		log_message('Error', login_result['fieldErrors'][0]['message'])
		return

	log_message('Info', '로그인 성공')

	# Set syllabus data
	syllabus_year = input('강의 계획서의 년도를 입력하세요 : ')
	syllabus_semester = input('강의 계획서의 학기를 입력하세요 : ')

	# Get all syllabus
	syllabus_result = hr.postRequest('https://klas.kw.ac.kr/std/cps/atnlc/LectrePlanStdList.do', {
		'selectYear': syllabus_year,
		'selecthakgi': syllabus_semester,
		'selectRadio': 'all'
	}).json()

	if len(syllabus_result) == 0:
		log_message('Error', '강의 계획서 정보가 없습니다.')
		return

	syllabus_count = len(syllabus_result)
	log_message('Info', '%d개의 강의 계획서 정보를 불러왔습니다.' % syllabus_count)
	
	# Alert message
	if input('강의실 정보를 불러옵니다. 이 작업은 서버에 부하를 줄 수 있습니다. [Y / N] : ') != 'Y':
		return

	lecture_list = []
	progress_count = 0

	# Parse syllabus info
	for syllabus_info in syllabus_result:
		lecture_info = get_lecture_info(syllabus_info)
		lecture_list += lecture_info

		progress_count += 1
		progress_bar(progress_count, syllabus_count)
		time.sleep(0.25)

	print('')
	log_message('Info', '모든 정보를 정상적으로 불러왔습니다.')

	# Save to file
	f = open('%d-%02d.json' % (int(syllabus_year), int(syllabus_semester)), 'w', encoding = 'utf8')
	f.write(json.dumps(lecture_list, ensure_ascii = False))
	f.close()

	log_message('Info', '모든 정보가 파일에 저장되었습니다.')

# Datas
building_name_changer = {
	'비': '비마관',
	'기': '기념관',
	'참': '참빛관',
	'문': '문화관',
	'옥': '옥의관',
	'연': '연구관',
	'화': '화도관',
	'누': '누리관',
	'한울': '한울관',
	'새빛': '새빛관',
	'한천': '한천재'
}

if __name__ == '__main__':
	hr = HttpRequest()
	main()