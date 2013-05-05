# -*- coding: utf-8 -*-
import gtk
import webkit
import subprocess
import os
from ConfigParser import SafeConfigParser
from locale import getdefaultlocale
import gettext
from time import sleep
if not os.path.isdir("./locale/"):
	gettext.bindtextdomain('hcc', '/usr/share/locale/')
else:
	gettext.bindtextdomain('hcc', './locale/')
gettext.textdomain('hcc')
_ = gettext.gettext

app_dir=os.getcwd()
lang=getdefaultlocale()[0].split('_')[0]
def execute(command, ret = True):
  	'''this execute shell command and return output
	execute() هذه الدالة لتنفيذ أمر بالطرفية واخراج الناتج'''
		
	if ret == True :
		p = os.popen(command)
		return p.readline()
		p.close
	else:
		p = subprocess.Popen(command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)

    
def functions(widget, nom,ida):
	
	'''This function is to receive functions from webkit
	functions(widget, nom,ida) لاستقبال الأوامر والدوال من المتصفح'''
	if ida=="about":
		'''launch About dialog
		ida==about فتح صندوق حوار عن البرنامج'''
		about = gtk.AboutDialog()
        	about.set_program_name("Helal Control Center")
        	about.set_version("1.0")
        	about.set_license('''This program is free software; you can redistribute it and/or modify it
under the terms of the GNU General Public License as published by
the Free Software Foundation; either version 2 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program; if not, write to the Free Software
Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston,
MA 02110-1301, USA. ''')
		about.set_authors(["Original Programer: Mohamed Mohsen <linuxer9@gmail.com>", "Modified by: M.Hanny Sabbagh <hannysabbagh@hotmail.com>"])
        	about.set_comments(_("helal control center"))
        	about.set_website("http://helallinux.com")
        	about.set_logo(gtk.gdk.pixbuf_new_from_file("frontend/images/hcc_logo.png"))
		about.set_icon_from_file('frontend/images/hcc_logo.png')
        	about.run()
        	about.destroy()

	if ida.startswith("pro_"):
		#TODO: التحقق من أن البرنامج يعمل \موجود وإظهار رسالة خطأ عند عدم تنفيذه.
		#if ida.startswith("pro_admin_"):
			#execute("gksu " + ida.split('pro_admin_')[1], ret=False)
		#else:
		execute(ida.split('pro_')[1], ret=False)
	if ida == "theme_browse":
		
		dialog = gtk.FileChooserDialog("Open..", None,
   	gtk.FILE_CHOOSER_ACTION_OPEN, (gtk.STOCK_CANCEL, gtk.RESPONSE_CANCEL, gtk.STOCK_OPEN, gtk.RESPONSE_OK))
		dialog.set_default_response(gtk.RESPONSE_OK)
		response = dialog.run()
		if response == gtk.RESPONSE_OK:
		    browser.execute_script('document.getElementById("file").value = "%s" ' %(dialog.get_filename()))
		elif response == gtk.RESPONSE_CANCEL:
		    print 'Closed, no files selected'
		dialog.destroy()

def get_info(info):
	'''this function is to get computer information
	get_info() هذه الدالة لجلب معلومات الجهاز '''
	if info=="os": return open('/etc/issue', 'r').read().split('\\n')[0]
	if info=="arc": return os.uname()[4]
	if info=="host": return os.uname()[1]	
	if info=="kernel": return os.uname()[0] +' '+ os.uname()[2]
	if info=="processor": return execute("cat /proc/cpuinfo | grep 'model name'").split(':')[1]
	if info=="mem": 
		mem = execute("free -m|awk '/^Mem:/{print $2}'")
		if  float(mem) > 1024:
			return str(round(float(mem) / 1024)) + " GB"
		else:
			return mem + " MB"
	if info=="gfx": return execute("lspci |grep VGA").split('controller:')[1].split('(rev')[0].split(',')[0]
	if info=="audio": return execute("lspci |grep Audio").split('device:')[1].split('(rev')[0].split(',')[0]
	if info=="eth": return execute("lspci |grep Ethernet").split('controller:')[1].split('(rev')[0].split(',')[0]
	if info=="desk": return execute("echo $XDG_CURRENT_DESKTOP")

def get_modules(section):
	'''this function is to get all modules in the dir "section" 
	get_modules() هذه الدالة لجلب الإضافات من الدليل المحدد وإخراج ناتج عند عدم وجود إضافات
	'''
	mod_dir=os.listdir("%s/modules/%s/" %(app_dir, section))
	if mod_dir==[]:
		return "<p>" + _("no modules found!") + "</p>"
	else:
		parser = SafeConfigParser()
		pro=""
		for i in mod_dir :
			parser.read("%s/modules/%s/%s" %(app_dir, section, i))
			'''Know if the icon exists
			ico معرفة إذا كانت الأيقونة موجودة بالمتغير '''
			ico =parser.get('module', 'ico')
			#check if the icon exists
			ico="icons/modules/" + ico
			
			#check if the name has a different language
			if parser.has_option('module', 'name[%s]' %(lang)):
				name = parser.get('module', 'name[%s]' %(lang))
			else: name = parser.get('module', 'name')
			
			#check if the description has a different language
			if parser.has_option('module', 'desc[%s]' %(lang)):
				desc = parser.get('module', 'desc[%s]' %(lang))
			else: desc = parser.get('module', 'desc')
			
			#if parser.has_option('module', 'root'):
				#if parser.get('module', 'root') == "true":
					#command = "admin_" + parser.get('module', 'command')
					#command = "gksu " + parser.get('module', 'command')
			#else:
			#admin or root weren't used from the version 0.3 
			command = parser.get('module', 'command')
				
			pro+='''<div id="launcher" onclick="changeTitle('pro_%s')" >
			<img src="%s" onerror='this.src = "icons/modules/notfound.png"'/>
			<h3>%s</h3>
			<span>%s</span>
			</div>''' % ( command, #command
			ico,   #icon 
			name,  #name 
			desc ) #description 
		return pro
		
def frontend_fill():
	'''This function is to build all the html document viewed
	frontend_fill() هذه الدالة لبناء ملف الواجهة html '''
	
	filee=open(app_dir + '/frontend/default.html', 'r')
	html=filee.read()
	if lang=="ar":
		html=html.replace("{css}", "ar")
	else:
		html=html.replace("{css}", "all")
	html=html.replace("{string_1}", _("System information"))
	html=html.replace("{string_2}", _("This is a quick overview of your system.."))
	html=html.replace("{string_3}", _("Computer"))
	html=html.replace("{string_4}", _("Operating system: "))
	html=html.replace("{string_5}", _("Processor: "))
	html=html.replace("{string_6}", _("Archticture: "))
	html=html.replace("{string_7}", _("Ram: "))
	html=html.replace("{string_8}", _("Devices"))
	html=html.replace("{string_9}", _("Graphics card: "))
	html=html.replace("{string_10}", _("Audio adapter: "))
	html=html.replace("{string_11}", _("Ethernet: "))
	html=html.replace("{string_12}", _("Misc"))
	html=html.replace("{string_13}", _("Host name: "))
	html=html.replace("{string_14}", _("Kernel: "))
	html=html.replace("{string_15}", _("Desktop: "))
	html=html.replace("{string_16}", _("Software & Packages"))
	html=html.replace("{string_17}", _("Working with software, packages and sources.."))
	html=html.replace("{string_18}", _("Desktop"))
	html=html.replace("{string_19}", _("Manage your desktop environment!"))
	html=html.replace("{string_20}", _("System"))
	html=html.replace("{string_21}", _("This is a set of useful tools for your system.."))
	html=html.replace("{string_22}", _("Hardware"))
	html=html.replace("{string_23}", _("here you can use Hardware tools, install drivers..etc"))
	html=html.replace("{string_24}", _("Other tools"))
	html=html.replace("{string_25}", _("all other tools that aren't related to any of these categories.."))
	html=html.replace("{string_26}", _("forum"))
	html=html.replace("{string_27}", _("help"))
	html=html.replace("{string_28}", _("Useful applications"))
	html=html.replace("{string_29}", _("here you can install some applications that are hard to setup..."))
	html=html.replace("{string_30}", _("Install GTK themes"))
	html=html.replace("{string_31}", _("select the theme you want to install in tar.gz "))
	html=html.replace("{string_32}", _("Get new GTK themes !"))
	html=html.replace("{string_33}", _("Browse"))
	html=html.replace("{string_34}", _("install"))
	html=html.replace("{string_35}", _("Install another Desktop environment"))
	html=html.replace("{string_36}", _("here you can install another desktop environments ... select one to install"))

	#system information معلومات الجهاز
	for i in ['os', 'arc', 'processor', 'mem', 'gfx', 'audio', 'eth', 'kernel', 'host', 'desk'] :
		html=html.replace("{%s}" %(i), get_info(i))
	#categories أقسام الإضافات
	for i in ['packs', 'system', 'desktop', 'hardware', 'other'] :
		html=html.replace("{%s_list}" %(i), get_modules(i))
	filee.close()
	return html


#splash screen
def spl_scr():
	splash=gtk.Window(gtk.WINDOW_TOPLEVEL)
	splash.set_position(gtk.WIN_POS_CENTER)
	splash.set_decorated(False)
	image = gtk.Image()
	image.set_from_file(app_dir + '/frontend/images/splash.png')
	splash.add(image)
	splash.show_all()
	while gtk.events_pending():
		gtk.main_iteration()
	frontend = frontend_fill()
	main(frontend)
	sleep(3)
	splash.destroy()
	gtk.main()
	
def main(frontend):
	global browser
	#TODO: تنظيم أفضل لهذه الأوامر
	window = gtk.Window()
	window.connect('destroy', gtk.main_quit)
	window.set_title(_("Helal Control Center"))
	window.set_size_request(774, 540)
	window.set_resizable(True)
	window.set_position(gtk.WIN_POS_CENTER)
	browser = webkit.WebView()
	swindow = gtk.ScrolledWindow()
	window.add(swindow)
	swindow.add(browser)
	window.set_icon_from_file('frontend/images/hcc_logo.png')
	window.show_all()
	browser.connect("title-changed", functions)
	browser.load_html_string(frontend, 'file://%s/frontend/' %(app_dir))
	#no right click menu
	settings = browser.get_settings()
	settings.set_property('enable-default-context-menu', False)
	browser.set_settings(settings) 

	
spl_scr()


