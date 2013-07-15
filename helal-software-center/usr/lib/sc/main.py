#!/usr/bin/python
# -*- coding: UTF-8 -*-

import Classes, sys, os, commands, gtk
import gtk.glade
import pygtk, gobject, thread, gettext
import tempfile
import threading
import webkit
import string
import Image
import StringIO
import ImageFont, ImageDraw, ImageOps
import time
import apt
import urllib
import thread
import glib
import dbus
from AptClient.AptClient import AptClient

from datetime import datetime
from subprocess import Popen, PIPE
from widgets.pathbar2 import NavigationBar
from widgets.searchentry import SearchEntry
import base64


if os.getuid() != 0:
    print "The software manager should be run as root."
    sys.exit(1)

pygtk.require("2.0")


def print_timing(func):
    def wrapper(*arg):
        t1 = time.time()
        res = func(*arg)
        t2 = time.time()
        print '%s took %0.3f ms' % (func.func_name, (t2-t1)*1000.0)
        return res
    return wrapper

# i18n
gettext.install("sc", "/usr/share/locale")

# i18n for menu item
menuName = _("Software Manager")
menuComment = _("Install new applications")

architecture = commands.getoutput("uname -a")
if (architecture.find("x86_64") >= 0):
    import ctypes
    libc = ctypes.CDLL('libc.so.6')
    libc.prctl(15, 'sc', 0, 0, 0)
else:
    import dl   
    if os.path.exists('/lib/libc.so.6'):
        libc = dl.open('/lib/libc.so.6')
        libc.call('prctl', 15, 'sc', 0, 0, 0)
    elif os.path.exists('/lib/i386-linux-gnu/libc.so.6'):
        libc = dl.open('/lib/i386-linux-gnu/libc.so.6')
        libc.call('prctl', 15, 'sc', 0, 0, 0)

gtk.gdk.threads_init()

COMMERCIAL_APPS = ["chromium-browser"]

def get_dbus_bus():
   bus = dbus.SystemBus()
   return bus


class APTProgressHandler(threading.Thread):
    def __init__(self, application, packages, wTree, apt_client):
        threading.Thread.__init__(self)
        self.application = application
        self.apt_client = apt_client
        self.wTree = wTree
        
        self.progressbar = wTree.get_widget("progressbar1")
        self.tree_transactions = wTree.get_widget("tree_transactions")
        self.packages = packages
        self.model = gtk.TreeStore(str, str, str, float, object)
        self.tree_transactions.set_model(self.model)
        self.tree_transactions.connect( "button-release-event", self.menuPopup )
        
        self.apt_client.connect("progress", self._on_apt_client_progress)
        self.apt_client.connect("task_ended", self._on_apt_client_task_ended)
    
    def _on_apt_client_progress(self, *args):
        self._update_display()

    def _on_apt_client_task_ended(self, *args):
        self._update_display()
    
    def _update_display(self):
        progress_info = self.apt_client.get_progress_info()
        task_ids = []
        for task in progress_info["tasks"]:
            task_is_new = True
            task_ids.append(task["task_id"])
            iter = self.model.get_iter_first()
            while iter is not None:
                if self.model.get_value(iter, 4)["task_id"] == task["task_id"]:
                    self.model.set_value(iter, 1, self.get_status_description(task))
                    self.model.set_value(iter, 2, "%d %%" % task["progress"])
                    self.model.set_value(iter, 3, task["progress"])
                    task_is_new = False
                iter = self.model.iter_next(iter)
            if task_is_new:
                iter = self.model.insert_before(None, None)
                self.model.set_value(iter, 0, self.get_role_description(task))
                self.model.set_value(iter, 1, self.get_status_description(task))
                self.model.set_value(iter, 2, "%d %%" % task["progress"])
                self.model.set_value(iter, 3, task["progress"])
                self.model.set_value(iter, 4, task)
        iter = self.model.get_iter_first()
        while iter is not None:
            if self.model.get_value(iter, 4)["task_id"] not in task_ids:
                task = self.model.get_value(iter, 4)
                iter_to_be_removed = iter
                iter = self.model.iter_next(iter)
                self.model.remove(iter_to_be_removed)
                if task["role"] in ["install", "remove", "upgrade"]:
                    pkg_name = task["task_params"]["package_name"]
                    cache = apt.Cache()
                    new_pkg = cache[pkg_name]
                    # Update packages
                    for package in self.packages:
                        if package.pkg.name == pkg_name:
                            package.pkg = new_pkg
                            # If the user is currently viewing this package in the browser,
                            # refresh the view to show that the package has been installed or uninstalled.
                            if self.application.navigation_bar.get_active().get_label() == pkg_name:
                                self.application.show_package(package, None)

                    # Update apps tree  
                    tree_applications = self.wTree.get_widget("tree_applications")
                    if tree_applications:
                        model_apps = tree_applications.get_model()
                        if isinstance(model_apps, gtk.TreeModelFilter):
                            model_apps = model_apps.get_model()

                        if model_apps is not None:
                            iter_apps = model_apps.get_iter_first()
                            while iter_apps is not None:
                                package = model_apps.get_value(iter_apps, 3)
                                if package.pkg.name == pkg_name:
                                    try:
                                        model_apps.set_value(iter_apps, 0, gtk.gdk.pixbuf_new_from_file_at_size(self.application.find_app_icon(package), 32, 32))
                                    except:
                                        try:
                                            model_apps.set_value(iter_apps, 0, gtk.gdk.pixbuf_new_from_file_at_size(self.application.find_app_icon_alternative(package), 32, 32))
                                        except:
                                            model_apps.set_value(iter_apps, 0, gtk.gdk.pixbuf_new_from_file_at_size(self.find_fallback_icon(package), 32, 32))
                                        
                                iter_apps = model_apps.iter_next(iter_apps)                    

                        # Update mixed apps tree                   
                        model_apps = self.wTree.get_widget("tree_mixed_applications").get_model()
                        if isinstance(model_apps, gtk.TreeModelFilter):
                            model_apps = model_apps.get_model()
                        if model_apps is not None:
                            iter_apps = model_apps.get_iter_first()
                            while iter_apps is not None:
                                package = model_apps.get_value(iter_apps, 3)
                                if package.pkg.name == pkg_name:
                                    try:
                                        model_apps.set_value(iter_apps, 0, gtk.gdk.pixbuf_new_from_file_at_size(self.application.find_app_icon(package), 32, 32))
                                    except:
                                        try:
                                            model_apps.set_value(iter_apps, 0, gtk.gdk.pixbuf_new_from_file_at_size(self.application.find_app_icon_alternative(package), 32, 32))
                                        except:
                                            model_apps.set_value(iter_apps, 0, gtk.gdk.pixbuf_new_from_file_at_size(self.find_fallback_icon(package), 32, 32))
                                iter_apps = model_apps.iter_next(iter_apps)
            else:
                iter = self.model.iter_next(iter)
        if progress_info["nb_tasks"] > 0:
            fraction = progress_info["progress"]
            progress = str(int(fraction)) + '%'
        else:
            fraction = 0
            progress = ""
        
        self.progressbar.set_text(progress)
        self.progressbar.set_fraction(fraction / 100.)

    def menuPopup( self, widget, event ):
        if event.button == 3:
            model, iter = self.tree_transactions.get_selection().get_selected()
            if iter is not None:
                task = model.get_value(iter, 4)
                menu = gtk.Menu()
                cancelMenuItem = gtk.MenuItem(_("Cancel the task: %s") % model.get_value(iter, 0))
                cancelMenuItem.set_sensitive(task["cancellable"])
                menu.append(cancelMenuItem)
                menu.show_all()
                cancelMenuItem.connect( "activate", self.cancelTask, task)
                menu.popup( None, None, None, event.button, event.time )

    def cancelTask(self, menu, task):
        self.apt_client.cancel_task(task["task_id"])
        self._update_display()
            
    def get_status_description(self, transaction):
        descriptions = {"waiting":_("Waiting"), "downloading":_("Downloading"), "running":_("Running"), "finished":_("Finished")}
        if "status" in transaction:
            if transaction["status"] in descriptions.keys():
                return descriptions[transaction["status"]]
            else:
                return transaction["status"]
        else:
            return ""
    
    def get_role_description(self, transaction):
        if "role" in transaction:
            if transaction["role"] == "install":
                return _("Installing %s") % transaction["task_params"]["package_name"]
	    elif transaction["role"] == "upgrade":
                return _("Upgrading %s") % transaction["task_params"]["package_name"]
            elif transaction["role"] == "remove":
                return _("Removing %s") % transaction["task_params"]["package_name"]
            elif transaction["role"] == "update_cache":
                return _("Updating cache")
            else:
                return _("No role set")
        else:
            return _("No role set")

class Category:

    def __init__(self, name, icon, sections, parent, categories):
        self.name = name
        self.icon = icon
        self.parent = parent
        self.subcategories = []
        self.packages = []
        self.sections = sections
        self.matchingPackages = []
        if parent is not None:
            parent.subcategories.append(self)
        categories.append(self)
        cat = self
        while cat.parent is not None:
            cat = cat.parent

class Package:

    def __init__(self, name, pkg):
        self.name = name
        self.pkg = pkg
        self.categories = []







class Application():
        
    PAGE_CATEGORIES = 0
    PAGE_MIXED = 1
    PAGE_PACKAGES = 2
    PAGE_DETAILS = 3
    PAGE_SEARCH = 4
    PAGE_TRANSACTIONS = 5


    NAVIGATION_HOME = 1
    NAVIGATION_SEARCH = 7
    NAVIGATION_CATEGORY = 3
    NAVIGATION_SEARCH_CATEGORY = 4
    NAVIGATION_SUB_CATEGORY = 5
    NAVIGATION_SEARCH_SUB_CATEGORY = 6
    NAVIGATION_ITEM = 7


    if os.path.exists("/usr/share/fonts/truetype/wqy/wqy-microhei.ttc"):
        FONT = "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc"
    else:
        FONT = "/usr/share/fonts/truetype/freefont/FreeSans.ttf"
        
    
    @print_timing    
    def __init__(self):
        self.add_categories()
        self.build_matched_packages()
        self.add_packages()
        self.cache_apt()
        # Build the GUI
        gladefile = "/usr/lib/sc/sc.glade"
        wTree = gtk.glade.XML(gladefile, "main_window")
        wTree.get_widget("main_window").set_title(_("Software Manager"))
        wTree.get_widget("main_window").set_icon_from_file("/usr/lib/sc/sc.png")
        wTree.get_widget("main_window").connect("delete_event", self.close_application)
        
        
        self.main_window = wTree.get_widget("main_window")

        self.apt_client = AptClient()
        self.apt_progress_handler = APTProgressHandler(self, self.packages, wTree, self.apt_client)
        


        if len(sys.argv) > 1 and sys.argv[1] == "list":
            # Print packages and their categories and exit
            self.export_listing()
            sys.exit(0)


        # Build the applications tables
        self.tree_applications = webkit.WebView()
        wTree.get_widget("tree_applications_scrolledview").add(self.tree_applications)
        template = open("/usr/lib/sc/data/templates/listView.html").read()
        self.tree_applications.load_html_string(template, "file:/")
        self.tree_applications.connect('title-changed', self._on_title_changed)
        #self.tree_mixed_applications = wTree.get_widget("tree_mixed_applications")
        self.tree_search = webkit.WebView()
        self.tree_search.load_html_string(template, "file:/")
        self.tree_search.connect('title-changed', self._on_title_changed)
        wTree.get_widget("scrolled_search").add(self.tree_search)
        self.tree_transactions = wTree.get_widget("tree_transactions")

        
        #self.build_application_tree(self.tree_mixed_applications)
        #self.build_application_tree(self.tree_search)
        self.loadHandlerID = -1
        self.acthread = threading.Thread(target=self.cache_apt)
        self.build_transactions_tree(self.tree_transactions)

        self.navigation_bar = NavigationBar()
        self.searchentry = SearchEntry()
        #self.searchentry.connect("terms-changed", self.on_search_terms_changed)
        self.searchentry.connect("activate", self.on_search_entry_activated)
        top_hbox = gtk.HBox()
        top_hbox.pack_start(self.navigation_bar, padding=6)
        top_hbox.pack_start(self.searchentry, expand=False, padding=6)
        wTree.get_widget("toolbar").pack_start(top_hbox, expand=False, padding=6)
        
        self.search_in_category_hbox = wTree.get_widget("search_in_category_hbox")
        self.message_search_in_category_label = wTree.get_widget("message_search_in_category_label")
        wTree.get_widget("show_all_results_button").connect("clicked", lambda w: self._show_all_search_results())
        wTree.get_widget("search_in_category_hbox_wrapper").modify_bg(gtk.STATE_NORMAL, gtk.gdk.color_parse("#F5F5B5"))
        
        self._search_in_category = self.root_category
        self._current_search_terms = ""

        self.notebook = wTree.get_widget("notebook1")

        sans26  =  ImageFont.truetype ( self.FONT, 26 )
        sans10  =  ImageFont.truetype ( self.FONT, 12 )

        # Build the category browsers
        self.browser = webkit.WebView()
        html = open("/usr/lib/sc/data/templates/CategoriesView.html").read()
        self.browser.load_html_string(html, "file:/")
        self.browser.connect("load-finished", self._on_load_finished)
        self.browser.connect('title-changed', self._on_title_changed)
        wTree.get_widget("scrolled_categories").add(self.browser)

        self.browser2 = webkit.WebView()
        self.browser2.load_html_string(html, "file:/")
        self.browser2.connect('title-changed', self._on_title_changed)
        wTree.get_widget("scrolled_mixed_categories").add(self.browser2)

        self.packageBrowser = webkit.WebView()
        wTree.get_widget("scrolled_details").add(self.packageBrowser)

        self.packageBrowser.connect('title-changed', self._on_title_changed)

        # kill right click menus in webkit views
        self.browser.connect("button-press-event", lambda w, e: e.button == 3)
        self.browser2.connect("button-press-event", lambda w, e: e.button == 3)
        self.packageBrowser.connect("button-press-event", lambda w, e: e.button == 3)


        wTree.get_widget("label_transactions_header").set_text(_("Active tasks:"))
        wTree.get_widget("progressbar1").hide_all()

        wTree.get_widget("button_transactions").connect("clicked", self.show_transactions)
        self._load_more_timer = None
        wTree.get_widget("main_window").show_all()
    
    
    def on_search_entry_activated(self, searchentry):
        terms = searchentry.get_text()
        if terms != "":
            self.show_search_results(terms)
    
    def close_window(self, widget, window):
        window.hide()

    def export_listing(self):
        # packages
        for package in self.packages:
            if package.pkg.name.endswith(":i386") or package.pkg.name.endswith(":amd64"):
                continue
            summary = ""
            if package.pkg.candidate is not None:
                summary = package.pkg.candidate.summary
            summary = summary.capitalize()
            description = ""
            version = ""
            homepage = ""
            strSize = ""
            if package.pkg.candidate is not None:
                description = package.pkg.candidate.description
                version = package.pkg.candidate.version
                homepage = package.pkg.candidate.homepage
                strSize = str(package.pkg.candidate.size) + _("B")
                if (package.pkg.candidate.size >= 1000):
                    strSize = str(package.pkg.candidate.size / 1000) + _("KB")
                if (package.pkg.candidate.size >= 1000000):
                    strSize = str(package.pkg.candidate.size / 1000000) + _("MB")
                if (package.pkg.candidate.size >= 1000000000):
                    strSize = str(package.pkg.candidate.size / 1000000000) + _("GB")

            description = description.capitalize()
            description = description.replace("\r\n", "<br>")
            description = description.replace("\n", "<br>")
            output = package.pkg.name + "#~#" + version + "#~#" + homepage + "#~#" + strSize + "#~#" + summary + "#~#" + description + "#~#"
            for category in package.categories:
                output = output + category.name + ":::"
            if output[-3:] == (":::"):
                output = output[:-3]
            print output

    def show_transactions(self, widget):
        self.notebook.set_current_page(self.PAGE_TRANSACTIONS)

    def close_window(self, widget, window, extra=None):
        try:
            window.hide_all()
        except:
            pass

    def build_application_tree(self, treeview):
        column0 = gtk.TreeViewColumn(_("Icon"), gtk.CellRendererPixbuf(), pixbuf=0)
        column0.set_sort_column_id(0)
        column0.set_resizable(True)

        column1 = gtk.TreeViewColumn(_("Application"), gtk.CellRendererText(), markup=1)
        column1.set_sort_column_id(1)
        column1.set_resizable(True)
        column1.set_sizing(gtk.TREE_VIEW_COLUMN_FIXED)
        column1.set_min_width(350)
        column1.set_max_width(350)

        column2 = gtk.TreeViewColumn(_("Score"), gtk.CellRendererPixbuf(), pixbuf=2)
        column2.set_sort_column_id(2)
        column2.set_resizable(True)
        
        #prevents multiple load finished handlers being hooked up to packageBrowser in show_package
        self.loadHandlerID = -1
        self.acthread = threading.Thread(target=self.cache_apt)
        
        treeview.append_column(column0)
        treeview.append_column(column1)
        treeview.append_column(column2)
        treeview.set_headers_visible(False)
        treeview.connect("row-activated", self.show_selected)
        treeview.show()
        #treeview.connect("row_activated", self.show_more_info)

        selection = treeview.get_selection()
        selection.set_mode(gtk.SELECTION_BROWSE)

        #selection.connect("changed", self.show_selected)

    def build_transactions_tree(self, treeview):
        column0 = gtk.TreeViewColumn(_("Task"), gtk.CellRendererText(), text=0)
        column0.set_resizable(True)

        column1 = gtk.TreeViewColumn(_("Status"), gtk.CellRendererText(), text=1)
        column1.set_resizable(True)

        column2 = gtk.TreeViewColumn(_("Progress"), gtk.CellRendererProgress(), text=2, value=3)
        column2.set_resizable(True)

        treeview.append_column(column0)
        treeview.append_column(column1)
        treeview.append_column(column2)
        treeview.set_headers_visible(True)
        treeview.show()


    def show_selected(self, tree, path, column):
        self.main_window.window.set_cursor(gtk.gdk.Cursor(gtk.gdk.WATCH))   
        self.main_window.set_sensitive(False)
        model = tree.get_model()
        iter = model.get_iter(path)

        #poll for end of apt caching when idle
        glib.idle_add(self.show_package_if_apt_cached, model.get_value(iter, 3), tree)
        #cache apt in a separate thread as blocks gui update
        self.acthread.start()

    def show_package_if_apt_cached(self, pkg, tree):
        if (self.acthread.isAlive()):
            self.acthread.join()
        
        self.show_package(pkg, tree)
        self.acthread = threading.Thread(target=self.cache_apt) #rebuild here for speed
        return False #false will remove this from gtk's list of idle functions
        #return True

    def cache_apt(self):
        self.cache = apt.Cache()

    def show_more_info(self, tree, path, column):
        model = tree.get_model()
        iter = model.get_iter(path)
        self.selected_package = model.get_value(iter, 3)

    def navigate(self, button, destination):

        if (destination == "search"):
            self.notebook.set_current_page(self.PAGE_SEARCH)
        else:
            self.searchentry.set_text("")
            self._search_in_category = self.root_category
            if isinstance(destination, Category):
                self._search_in_category = destination
                if len(destination.subcategories) > 0:
                    if len(destination.packages) > 0:
                        self.notebook.set_current_page(self.PAGE_MIXED)
                    else:
                        self.notebook.set_current_page(self.PAGE_CATEGORIES)
                else:
                    self.notebook.set_current_page(self.PAGE_PACKAGES)
            elif isinstance(destination, Package):
                self.notebook.set_current_page(self.PAGE_DETAILS)



    def close_application(self, window, event=None, exit_code=0):
        self.apt_client.call_on_completion(lambda c: self.do_close_application(c), exit_code)
        window.hide()
    
    def do_close_application(self, exit_code):
        if exit_code == 0:
            pid = os.getpid()
            os.system("kill -9 %s &" % pid)
        else:            
            gtk.main_quit()
            sys.exit(exit_code)

    def _on_load_finished(self, view, frame):
        # Get the categories
        self.show_category(self.root_category)

    def _on_package_load_finished(self, view, frame, ):

        self.main_window.set_sensitive(True)
        self.main_window.window.set_cursor(None)

    def on_category_clicked(self, name):
        for category in self.categories:
            if category.name == name:
                self.show_category(category)

    def on_package_clicked(self, name):
        for package in self.glo_cat:
            if package.name == name:
                self.show_package(package, None)
                
    def on_button_clicked(self):        
        package = self.current_package
        if package is not None:             
            if package.pkg.is_installed:
                self.apt_client.remove_package(package.pkg.name)
	    elif package.pkg.is_upgradable:
                self.apt_client.remove_package(package.pkg.name)
                self.apt_client.install_package(package.pkg.name)
            else:
                self.apt_client.install_package(package.pkg.name)
    def get_screenshot(self, package_name):
        #http://screenshots.debian.net/screenshot/synaptic
        ##http://screenshots.debian.net/thumbnail/synaptic
        os.system("mkdir -p ~/.screenshots/")
        if os.path.isfile("/root/.screenshots/" + package_name + ".png") == False:
            os.system("wget -O ~/.screenshots/" + package_name + ".png http://screenshots.debian.net/screenshot/" + package_name)
        return "/root/.screenshots/" + package_name + ".png"
        
    def on_screenshot_clicked(self):
        package = self.current_package
        gladefile = "/usr/lib/sc/sc.glade"
        wTree = gtk.glade.XML(gladefile, "screenshot_window")
        #wTree.get_widget("screenshot_window").connect("delete_event", close_window, wTree.get_widget("screenshot_window"))
        #wTree.get_widget("button_screen_close").connect("clicked", close_window, wTree.get_widget("screenshot_window"))
        wTree.get_widget("image_screen").set_from_pixbuf(gtk.gdk.pixbuf_new_from_file(self.get_screenshot(self.current_package.pkg.name)))
        #wTree.get_widget("button_screen").connect("clicked", close_window, wTree.get_widget("screenshot_window"))      
        wTree.get_widget("screenshot_window").show_all()

    def on_website_clicked(self):
        package = self.current_package
        os.system("xdg-open " + self.current_package.pkg.candidate.homepage + " &")

    def _on_title_changed(self, view, frame, title):
        # no op - needed to reset the title after a action so that
        #        the action can be triggered again
        if title.startswith("nop"):
            return
        # call directive looks like:
        #  "call:func:arg1,arg2"
        #  "call:func"
        if title.startswith("call:"):
            args_str = ""
            args_list = []
            # try long form (with arguments) first
            try:
                (t,funcname,args_str) = title.split(":")
            except ValueError:
                # now try short (without arguments)
                (t,funcname) = title.split(":")
            if args_str:
                args_list = args_str.split(",")
            # see if we have it and if it can be called
            f = getattr(self, funcname)
            if f and callable(f):
                f(*args_list)
            # now we need to reset the title
            self.browser.execute_script('document.title = "nop"')

    @print_timing
    def add_categories(self):
        self.categories = []
        self.root_category = Category(_("Categories"), "applications-other", None, None, self.categories)
        
        featured = Category(_("Featured"), "/usr/lib/sc/data/templates/featured.svg", None, self.root_category, self.categories)
        featured.matchingPackages = self.file_to_array("/usr/lib/sc/categories/featured.list")


        #self.category_all = Category(_("All Packages"), "applications-other", None, self.root_category, self.categories)
        
        internet = Category(_("Internet"), "applications-internet", None, self.root_category, self.categories)
        subcat = Category(_("Web"), "applications-internet", ("web", "net"), internet, self.categories)
        subcat.matchingPackages = self.file_to_array("/usr/lib/sc/categories/internet-web.list")
        subcat = Category(_("Email"), "applications-internet", ("mail"), internet, self.categories)
        subcat.matchingPackages = self.file_to_array("/usr/lib/sc/categories/internet-email.list")
        subcat = Category(_("Chat"), "applications-internet", None, internet, self.categories)
        subcat.matchingPackages = self.file_to_array("/usr/lib/sc/categories/internet-chat.list")
        subcat = Category(_("File sharing"), "applications-internet", None, internet, self.categories)
        subcat.matchingPackages = self.file_to_array("/usr/lib/sc/categories/internet-filesharing.list")
        
        cat = Category(_("Sound and video"), "applications-multimedia", ("multimedia", "video"), self.root_category, self.categories)
        cat.matchingPackages = self.file_to_array("/usr/lib/sc/categories/sound-video.list")
        
        graphics = Category(_("Graphics"), "applications-graphics", ("graphics"), self.root_category, self.categories)
        graphics.matchingPackages = self.file_to_array("/usr/lib/sc/categories/graphics.list")
        subcat = Category(_("3D"), "applications-graphics", None, graphics, self.categories)
        subcat.matchingPackages = self.file_to_array("/usr/lib/sc/categories/graphics-3d.list")
        subcat = Category(_("Drawing"), "applications-graphics", None, graphics, self.categories)
        subcat.matchingPackages = self.file_to_array("/usr/lib/sc/categories/graphics-drawing.list")
        subcat = Category(_("Photography"), "applications-graphics", None, graphics, self.categories)
        subcat.matchingPackages = self.file_to_array("/usr/lib/sc/categories/graphics-photography.list")
        subcat = Category(_("Publishing"), "applications-graphics", None, graphics, self.categories)
        subcat.matchingPackages = self.file_to_array("/usr/lib/sc/categories/graphics-publishing.list")
        subcat = Category(_("Scanning"), "applications-graphics", None, graphics, self.categories)
        subcat.matchingPackages = self.file_to_array("/usr/lib/sc/categories/graphics-scanning.list")
        subcat = Category(_("Viewers"), "applications-graphics", None, graphics, self.categories)
        subcat.matchingPackages = self.file_to_array("/usr/lib/sc/categories/graphics-viewers.list")
        
        Category(_("Office"), "applications-office", ("office", "editors"), self.root_category, self.categories)
        
        games = Category(_("Games"), "applications-games", ("games"), self.root_category, self.categories)
        subcat = Category(_("Board games"), "applications-games", None, games, self.categories)
        subcat.matchingPackages = self.file_to_array("/usr/lib/sc/categories/games-board.list")
        subcat = Category(_("First-person shooters"), "applications-games", None, games, self.categories)
        subcat.matchingPackages = self.file_to_array("/usr/lib/sc/categories/games-fps.list")
        subcat = Category(_("Real-time strategy"), "applications-games", None, games, self.categories)
        subcat.matchingPackages = self.file_to_array("/usr/lib/sc/categories/games-rts.list")
        subcat = Category(_("Turn-based strategy"), "applications-games", None, games, self.categories)
        subcat.matchingPackages = self.file_to_array("/usr/lib/sc/categories/games-tbs.list")
        subcat = Category(_("Emulators"), "applications-games", None, games, self.categories)
        subcat.matchingPackages = self.file_to_array("/usr/lib/sc/categories/games-emulators.list")
        subcat = Category(_("Simulation and racing"), "applications-games", None, games, self.categories)
        subcat.matchingPackages = self.file_to_array("/usr/lib/sc/categories/games-simulations.list")
        
        Category(_("Accessories"), "applications-utilities", ("accessories", "utils"), self.root_category, self.categories)
        islam = Category(_("Islamic"), "/usr/share/sc/data/icons/categories/icon-islam.svg", None, self.root_category, self.categories)
        islam.matchingPackages = self.file_to_array("/usr/lib/sc/categories/islamic-software.list")
        
        cat = Category(_("System tools"), "applications-system", ("system", "admin"), self.root_category, self.categories)
        cat.matchingPackages = self.file_to_array("/usr/lib/sc/categories/system-tools.list")

        subcat = Category(_("Fonts"), "applications-fonts", ("fonts"), self.root_category, self.categories)
        subcat.matchingPackages = self.file_to_array("/usr/lib/sc/categories/fonts.list")
               
        subcat = Category(_("Education"), "applications-science", ("science", "math", "education"), self.root_category, self.categories)
        subcat.matchingPackages = self.file_to_array("/usr/lib/sc/categories/education.list")

        Category(_("Programming"), "applications-development", ("devel", "java"), self.root_category, self.categories)
        #self.category_other = Category(_("Other"), "applications-other", None, self.root_category, self.categories)        

    def file_to_array(self, filename):
        array = []
        f = open(filename)
        for line in f:
            line = line.replace("\n","").replace("\r","").strip();
            if line != "":
                array.append(line)
        return array


    @print_timing
    def build_matched_packages(self):
        # Build a list of matched packages
        self.matchedPackages = []
        for category in self.categories:
            self.matchedPackages.extend(category.matchingPackages)
        self.matchedPackages.sort()

    @print_timing
    def add_packages(self):
        self.packages = []
        self.packages_dict = {}
        cache = apt.Cache()         
                                                
        for pkg in cache:
            package = Package(pkg.name, pkg)
            self.packages.append(package)
            self.packages_dict[pkg.name] = package
            #self.category_all.packages.append(package)

            # If the package is not a "matching package", find categories with matching sections
            if (pkg.name not in self.matchedPackages):
                section = pkg.section
                if "/" in section:
                    section = section.split("/")[1]
                for category in self.categories:
                    if category.sections is not None:
                        if section in category.sections:
                            self.add_package_to_category(package, category)
     
        # Process matching packages
        for category in self.categories:
            for package_name in category.matchingPackages:              
                try:
                    package = self.packages_dict[package_name]                  
                    self.add_package_to_category(package, category)
                except Exception, detail:
                    pass
                    #print detail
        
        

    def add_package_to_category(self, package, category):
        if category.parent is not None:
            if category not in package.categories:
                package.categories.append(category)
                category.packages.append(package)
            self.add_package_to_category(package, category.parent)

    
    
    def _on_tree_applications_scrolled(self, adjustment):
        if self._load_more_timer:
            gobject.source_remove(self._load_more_timer)
        self._load_more_timer = gobject.timeout_add(500, self._load_more_packages)
    
    def _load_more_packages(self):
        self._load_more_timer = None
        return False
    
    def display_packages_list(self, packages_list):
        sans26  =  ImageFont.truetype ( self.FONT, 26 )
        sans10  =  ImageFont.truetype ( self.FONT, 12 )
        
        for package in packages_list:
            
            if package.name in COMMERCIAL_APPS:
                continue
            
            iter = self._model_applications.insert_before(None, None)
            try:
                self._model_applications.set_value(iter, 0, gtk.gdk.pixbuf_new_from_file_at_size(self.find_app_icon(package), 32, 32))
            except:
                try:                
                    self._model_applications.set_value(iter, 0, gtk.gdk.pixbuf_new_from_file_at_size(self.find_app_icon_alternative(package), 32, 32))
                except:
                    self._model_applications.set_value(iter, 0, gtk.gdk.pixbuf_new_from_file_at_size(self.find_fallback_icon(package), 32, 32))
            summary = ""
            if package.pkg.candidate is not None:
                summary = package.pkg.candidate.summary
                summary = unicode(summary, 'UTF-8', 'replace')
                summary = summary.replace("<", "&lt;")
                summary = summary.replace("&", "&amp;")

            self._model_applications.set_value(iter, 1, "%s\n<small><span foreground='#555555'>%s</span></small>" % (package.name, summary.capitalize()))


            self._model_applications.set_value(iter, 3, package)
    
    @print_timing
    def show_category(self, category):
        self._search_in_category = category
        # Load subcategories
        if len(category.subcategories) > 0:
            if len(category.packages) == 0:
                # Show categories page
                browser = self.browser
                size = 64
            else:
                # Show mixed page
                browser = self.browser2
                size = 48

            browser.execute_script('clearCategories()')
            theme = gtk.icon_theme_get_default()
            for cat in category.subcategories:
                icon = None
                if theme.has_icon(cat.icon):
                    iconInfo = theme.lookup_icon(cat.icon, size, 0)
                    if iconInfo and os.path.exists(iconInfo.get_filename()):
                        icon = iconInfo.get_filename()              
                if icon == None:
                    if os.path.exists(cat.icon):
                        icon = cat.icon
                    else:
                        iconInfo = theme.lookup_icon("applications-other", size, 0)
                        if iconInfo and os.path.exists(iconInfo.get_filename()):
                            icon = iconInfo.get_filename()
                browser.execute_script('addCategory("%s", "%s", "%s")' % (cat.name, _("%d packages") % len(cat.packages), icon))
        tree_applications = self.tree_applications
        self.glo_cat = category.packages
        tree_applications.execute_script('Clear()')
        for package in category.packages:
         try:
            icon = self.find_app_icon(package)
         except:
            try:
               icon = self.find_app_icon_alternative(package)
            except:
               icon = self.find_fallback_icon(package)
         summary = ""
         if package.pkg.candidate is not None:
                summary = package.pkg.candidate.summary
                summary = unicode(summary, 'UTF-8', 'replace')
                summary = summary.replace("<", "&lt;")
                summary = summary.replace("&", "&amp;")
         tree_applications.execute_script('addPackage("%s", "%s", "%s")' %(package.name, icon, summary))
         #except: pass
        # Update the navigation bar
        if category == self.root_category:
            self.navigation_bar.add_with_id(category.name, self.navigate, self.NAVIGATION_HOME, category)
        elif category.parent == self.root_category:
            self.navigation_bar.add_with_id(category.name, self.navigate, self.NAVIGATION_CATEGORY, category)
        else:
            self.navigation_bar.add_with_id(category.name, self.navigate, self.NAVIGATION_SUB_CATEGORY, category)

    def find_fallback_icon(self, package):
        if package.pkg.is_installed:
            icon_path = "/usr/lib/sc/data/installed.png"
	elif package.pkg.is_upgradable:
	    icon_path = "/usr/lib/sc/data/emblem-installed.png"
        else:
            icon_path = "/usr/lib/sc/data/available.png"
        return icon_path
            
    def find_app_icon_alternative(self, package):
        icon_path = None
        if package.pkg.is_installed:
            icon_path = "/usr/share/sc/installed/%s" % package.name
            if os.path.exists(icon_path + ".png"):
                icon_path = icon_path + ".png"
            elif os.path.exists(icon_path + ".xpm"):
                icon_path = icon_path + ".xpm"
            else:
                # Else, default to generic icons
                icon_path = "/usr/lib/sc/data/installed.png"

	elif package.pkg.is_upgradable:
            icon_path = "/usr/share/sc/installed/%s" % package.name
            if os.path.exists(icon_path + ".png"):
                icon_path = icon_path + ".png"
            elif os.path.exists(icon_path + ".xpm"):
                icon_path = icon_path + ".xpm"
            else:
                # Else, default to generic icons
                icon_path = "/usr/lib/sc/data/emblem-installed.png"



        else:          
            # Try the Icon theme first
            theme = gtk.icon_theme_get_default()
            if theme.has_icon(package.name):
                iconInfo = theme.lookup_icon(package.name, 32, 0)
                if iconInfo and os.path.exists(iconInfo.get_filename()):
                    icon_path = iconInfo.get_filename()
            else:
                # Try our-icons then
                icon_path = "/usr/share/sc/icons/%s" % package.name
                if os.path.exists(icon_path + ".png"):
                    icon_path = icon_path + ".png"
                elif os.path.exists(icon_path + ".xpm"):
                    icon_path = icon_path + ".xpm"
                else:
                    # Else, default to generic icons
                    icon_path = "/usr/lib/sc/data/available.png"
        return icon_path
    
    def find_app_icon(self, package):
        icon_path = None
        # Try the Icon theme first
        theme = gtk.icon_theme_get_default()
        if theme.has_icon(package.name):
            iconInfo = theme.lookup_icon(package.name, 32, 0)
            if iconInfo and os.path.exists(iconInfo.get_filename()):
                icon_path = iconInfo.get_filename()
            
        if icon_path is not None:
            if package.pkg.is_installed:
                im=Image.open(icon_path)
                bg_w,bg_h=im.size
                im2=Image.open("/usr/lib/sc/data/emblem-installed.png")
                img_w,img_h=im2.size 
                offset=(17,17)         
                im.paste(im2, offset,im2)
                tmpFile = tempfile.NamedTemporaryFile(delete=False)
                im.save (tmpFile.name + ".png")             
                icon_path = tmpFile.name + ".png"   

            if package.pkg.is_upgradable:
                im=Image.open(icon_path)
                bg_w,bg_h=im.size
                im2=Image.open("/usr/lib/sc/data/available.png")
                img_w,img_h=im2.size 
                offset=(17,17)         
                im.paste(im2, offset,im2)
                tmpFile = tempfile.NamedTemporaryFile(delete=False)
                im.save (tmpFile.name + ".png")             
                icon_path = tmpFile.name + ".png"              
        else:
            # Try our-icons then
            if package.pkg.is_installed:
                icon_path = "/usr/share/sc/icons/installed/%s" % package.name
	    elif package.pkg.is_upgradable:
		icon_path = "/usr/share/sc/icons/%s" % package.name
            else:
                icon_path = "/usr/share/sc/icons/%s" % package.name
                
            if os.path.exists(icon_path + ".png"):
                icon_path = icon_path + ".png"
            elif os.path.exists(icon_path + ".xpm"):
                icon_path = icon_path + ".xpm"
            else:
                # Else, default to generic icons                
                if package.pkg.is_installed:
                    icon_path = "/usr/lib/sc/data/installed.png"
		elif package.pkg.is_upgradable:
		    icon_path = "/usr/share/sc/data/icons/categories/188.png"
                else:
                    icon_path = "/usr/lib/sc/data/available.png"
                                            
        return icon_path
    
                
    def find_large_app_icon(self, package):
        theme = gtk.icon_theme_get_default()
        if theme.has_icon(package.name):
            iconInfo = theme.lookup_icon(package.name, 64, 0)
            if iconInfo and os.path.exists(iconInfo.get_filename()):
                return iconInfo.get_filename()
    
        iconInfo = theme.lookup_icon("applications-other", 64, 0)       
        return iconInfo.get_filename()
    
    def _show_all_search_results(self):
        self._search_in_category = self.root_category
        self.show_search_results(self._current_search_terms)

    def show_search_results(self, terms):
        self._current_search_terms = terms
        
        # Load packages into self.tree_search
        #model_applications = gtk.TreeStore(gtk.gdk.Pixbuf, str, gtk.gdk.Pixbuf, object)

        #self.model_filter = model_applications.filter_new()
        #self.model_filter.set_visible_func(self.visible_func)

        #sans26  =  ImageFont.truetype ( self.FONT, 26 )
        #sans10  =  ImageFont.truetype ( self.FONT, 12 )
        self.tree_search.execute_script('Clear()')
        if self._search_in_category == self.root_category:
            packages = self.packages
        else:
            packages = self._search_in_category.packages
        #packages.sort(self.package_compare)
        for package in packages:
            visible = False
            if terms.upper() in package.pkg.name.upper():
                visible = True
            else:
                if (package.pkg.candidate is not None):
                        if (terms.upper() in package.pkg.candidate.summary.upper()):
                               visible = True


            if visible:
                #iter = model_applications.insert_before(None, None)
                #try:
                #    model_applications.set_value(iter, 0, gtk.gdk.pixbuf_new_from_file_at_size(self.find_app_icon(package), 32, 32))
                #except:
                #    try:
                #        model_applications.set_value(iter, 0, gtk.gdk.pixbuf_new_from_file_at_size(self.find_app_icon_alternative(package), 32, 32))
                #    except:
                #        model_applications.set_value(iter, 0, gtk.gdk.pixbuf_new_from_file_at_size(self.find_fallback_icon(package), 32, 32))
                try:
                	icon = self.find_app_icon(package)
                except:
                	try:
                		icon = self.find_app_icon_alternative(package)
                	except:
                		icon = self.find_fallback_icon(package)
                summary = ""
                if package.pkg.candidate is not None:
                    summary = package.pkg.candidate.summary
                    summary = unicode(summary, 'UTF-8', 'replace')
                    summary = summary.replace("<", "&lt;")
                    summary = summary.replace("&", "&amp;")
                self.tree_search.execute_script('addPackage("%s", "%s", "%s")' %(package.name, icon, summary))

                #model_applications.set_value(iter, 1, "%s\n<small><span foreground='#555555'>%s</span></small>" % (package.name, summary.capitalize()))
                #model_applications.set_value(iter, 3, package)

        #self.tree_search.set_model(self.model_filter)
        #del model_applications
        if self._search_in_category != self.root_category:
            self.search_in_category_hbox.show()
            self.message_search_in_category_label.set_markup("<b>%s</b>" % (_("Only results in category \"%s\" are shown." % self._search_in_category.name)))
        if self._search_in_category == self.root_category:
            self.search_in_category_hbox.hide()
            self.navigation_bar.add_with_id(self._search_in_category.name, self.navigate, self.NAVIGATION_HOME, self._search_in_category)
            navigation_id = self.NAVIGATION_SEARCH
        elif self._search_in_category.parent == self.root_category:
            self.navigation_bar.add_with_id(self._search_in_category.name, self.navigate, self.NAVIGATION_CATEGORY, self._search_in_category)
            navigation_id = self.NAVIGATION_SEARCH_CATEGORY
        else:
            self.navigation_bar.add_with_id(self._search_in_category.name, self.navigate, self.NAVIGATION_SUB_CATEGORY, self._search_in_category)
            navigation_id = self.NAVIGATION_SEARCH_SUB_CATEGORY
        self.navigation_bar.add_with_id(_("Search results"), self.navigate, navigation_id, "search")
        

    def visible_func(self, model, iter):
        package = model.get_value(iter, 3)
        if package is not None:
            if package.pkg is not None:
                return True
        return False

    @print_timing
    def show_package(self, package, tree):

        self.current_package = package
                
        # Load package info
        subs = {}
        
        font_description = gtk.Label("pango").get_pango_context().get_font_description()
        subs['font_family'] = font_description.get_family()
        try:
            subs['font_weight'] = font_description.get_weight().real
        except:
            subs['font_weight'] = font_description.get_weight()   
        subs['font_style'] = font_description.get_style().value_nick        
        subs['font_size'] = font_description.get_size() / 1024      


        subs['iconbig'] = self.find_large_app_icon(package)

        subs['appname'] = package.name
        subs['pkgname'] = package.pkg.name
        subs['description'] = package.pkg.candidate.description
        subs['description'] = subs['description'].replace('\n','<br />\n')
        subs['summary'] = package.pkg.candidate.summary.capitalize()

        impacted_packages = []    

        
        pkg = self.cache[package.name]
	if package.pkg.is_upgradable:
	    pkg.mark_delete(True, True)
	    pkg.mark_install()
        elif package.pkg.is_installed:
            pkg.mark_delete(True, True)
        else:
            pkg.mark_install()
    
        changes = self.cache.get_changes()
        for pkg in changes:
            if (pkg.is_installed):
                impacted_packages.append(_("%s (removed)") % pkg.name)
	    elif (pkg.is_upgradable):
		impacted_packages.append(_("%s (upgradable)") % pkg.name)
            else:
                impacted_packages.append(_("%s (installed)") % pkg.name)
        
        downloadSize = str(self.cache.required_download) + _("B")
        if (self.cache.required_download >= 1000):
            downloadSize = str(self.cache.required_download / 1000) + _("KB")
        if (self.cache.required_download >= 1000000):
            downloadSize = str(self.cache.required_download / 1000000) + _("MB")
        if (self.cache.required_download >= 1000000000):
            downloadSize = str(self.cache.required_download / 1000000000) + _("GB")
                   
        required_space = self.cache.required_space
        if (required_space < 0):
            required_space = (-1) * required_space          
        localSize = str(required_space) + _("B")
        if (required_space >= 1000):
            localSize = str(required_space / 1000) + _("KB")
        if (required_space >= 1000000):
            localSize = str(required_space / 1000000) + _("MB")
        if (required_space >= 1000000000):
            localSize = str(required_space / 1000000000) + _("GB")

        subs['sizeLabel'] = _("Size:")
        subs['versionLabel'] = _("Version:")
        subs['impactLabel'] = _("Impact on packages:")
        subs['detailsLabel'] = _("Details")
        
        if package.pkg.is_installed:
            if self.cache.required_space < 0:
                subs['sizeinfo'] = _("%(localSize)s of disk space freed") % {'localSize': localSize}
            else:
                subs['sizeinfo'] = _("%(localSize)s of disk space required") % {'localSize': localSize}

	elif package.pkg.is_upgradable:
            if self.cache.required_space < 0:
                subs['sizeinfo'] = _("%(localSize)s of disk space freed") % {'localSize': localSize}
            else:
                subs['sizeinfo'] = _("%(localSize)s of disk space required") % {'localSize': localSize}

        else:
            if self.cache.required_space < 0:
                subs['sizeinfo'] = _("%(downloadSize)s to download, %(localSize)s of disk space freed") % {'downloadSize': downloadSize, 'localSize': localSize}
            else:
                subs['sizeinfo'] = _("%(downloadSize)s to download, %(localSize)s of disk space required") % {'downloadSize': downloadSize, 'localSize': localSize}
            
        subs['packagesinfo'] = (', '.join(name for name in impacted_packages))

        if len(package.pkg.candidate.homepage) > 0:
            subs['homepage'] = package.pkg.candidate.homepage
            subs['homepage_button_visibility'] = "visible"
        else:
            subs['homepage'] = ""
            subs['homepage_button_visibility'] = "hidden"
        
        direction = gtk.widget_get_default_direction()
        if direction ==  gtk.TEXT_DIR_RTL:
            subs['text_direction'] = 'DIR="RTL"'
        elif direction ==  gtk.TEXT_DIR_LTR:
            subs['text_direction'] = 'DIR="LTR"'

	if package.pkg.is_upgradable:
            subs['action_button_label'] = _("Upgrade")
            subs['action_button_value'] = "upgrade"
            subs['version'] = package.pkg.candidate.version
            subs['action_button_description'] = _("Upgradable")
            subs['iconstatus'] = "/usr/share/sc/data/icons/categories/188.png"


        elif package.pkg.is_installed:
            subs['action_button_label'] = _("Remove")
            subs['action_button_value'] = "remove"
            subs['version'] = package.pkg.installed.version
            subs['action_button_description'] = _("Installed")
            subs['iconstatus'] = "/usr/lib/sc/data/installed.png"

        else:
            subs['action_button_label'] = _("Install")
            subs['action_button_value'] = "install"
            subs['version'] = package.pkg.candidate.version
            subs['action_button_description'] = _("Not installed")
            subs['iconstatus'] = "/usr/lib/sc/data/available.png"

        template = open("/usr/lib/sc/data/templates/PackageView.html").read()
        html = string.Template(template).safe_substitute(subs)
        self.packageBrowser.load_html_string(html, "file:/")
        
        if self.loadHandlerID != -1:
            self.packageBrowser.disconnect(self.loadHandlerID)
        
        self.loadHandlerID = self.packageBrowser.connect("load-finished", self._on_package_load_finished)       

        # Update the navigation bar
        self.navigation_bar.add_with_id(package.name, self.navigate, self.NAVIGATION_ITEM, package)

if __name__ == "__main__":
    model = Classes.Model()
    Application()

    gtk.main()
