from flask import *
from flask_user import *
from flask.ext import menu
from app import app
from app.models import *
from app.tasks.importtasks import makeVCSRelease

from .utils import *

from flask_wtf import FlaskForm
from wtforms import *
from wtforms.validators import *
from wtforms.ext.sqlalchemy.fields import QuerySelectField, QuerySelectMultipleField


# TODO: the following could be made into one route, except I"m not sure how
# to do the menu

@menu.register_menu(app, ".mods", "Mods", order=11, endpoint_arguments_constructor=lambda: { 'type': 'mod' })
@menu.register_menu(app, ".games", "Games", order=12, endpoint_arguments_constructor=lambda: { 'type': 'game' })
@menu.register_menu(app, ".txp", "Texture Packs", order=13, endpoint_arguments_constructor=lambda: { 'type': 'txp' })
@app.route("/packages/")
def packages_page():
	type = request.args.get("type")
	if type is not None:
		type = PackageType[type.upper()]

	title = "Packages"
	query = Package.query

	if type is not None:
		title = type.value + "s"
		query = query.filter_by(type=type, approved=True)

	search = request.args.get("q")
	if search is not None:
		query = query.filter(Package.title.contains(search))

	if shouldReturnJson():
		pkgs = [package.getAsDictionary(app.config["BASE_URL"]) \
				for package in query.all() if package.getDownloadRelease() is not None]
		return jsonify(pkgs)
	else:
		tags = Tag.query.all()
		return render_template("packages/list.html", title=title, packages=query.all(), \
				query=search, tags=tags, type=None if type is None else type.toName())


def canSeeWorkQueue():
	return Permission.APPROVE_NEW.check(current_user) or \
		Permission.APPROVE_RELEASE.check(current_user) or \
			Permission.APPROVE_CHANGES.check(current_user)

@menu.register_menu(app, ".todo", "Work Queue", order=20, visible_when=canSeeWorkQueue)
@app.route("/todo/")
@login_required
def todo_page():
	canApproveNew = Permission.APPROVE_NEW.check(current_user)
	canApproveRel = Permission.APPROVE_RELEASE.check(current_user)

	packages = None
	if canApproveNew:
		packages = Package.query.filter_by(approved=False).all()

	releases = None
	if canApproveRel:
		releases = PackageRelease.query.filter_by(approved=False).all()

	return render_template("todo.html", title="Reports and Work Queue",
		approve_new=packages, releases=releases,
		canApproveNew=canApproveNew, canApproveRel=canApproveRel)

def getReleases(package):
	if package.checkPerm(current_user, Permission.MAKE_RELEASE):
		return package.releases
	else:
		return [rel for rel in package.releases if rel.approved]


@app.route("/packages/<author>/<name>/")
@is_package_page
def package_page(package):
	if shouldReturnJson():
		return jsonify(package.getAsDictionary(app.config["BASE_URL"]))
	else:
		clearNotifications(package.getDetailsURL())

		releases = getReleases(package)
		requests = [r for r in package.requests if r.status == 0]
		return render_template("packages/view.html", package=package, releases=releases, requests=requests)


@app.route("/packages/<author>/<name>/download/")
@is_package_page
def package_download_page(package):
	release = package.getDownloadRelease()

	if release is None:
		if "application/zip" in request.accept_mimetypes and \
				not "text/html" in request.accept_mimetypes:
			return "", 204
		else:
			flash("No download available.", "error")
			return redirect(package.getDetailsURL())
	else:
		return redirect(release.url, code=302)


class PackageForm(FlaskForm):
	name         = StringField("Name", [InputRequired(), Length(1, 20), Regexp("^[a-z0-9_]", 0, "Lower case letters (a-z), digits (0-9), and underscores (_) only")])
	title        = StringField("Title", [InputRequired(), Length(3, 50)])
	shortDesc    = StringField("Short Description", [InputRequired(), Length(1,200)])
	desc         = TextAreaField("Long Description", [Optional(), Length(0,10000)])
	type         = SelectField("Type", [InputRequired()], choices=PackageType.choices(), coerce=PackageType.coerce, default=PackageType.MOD)
	license      = QuerySelectField("License", [InputRequired()], query_factory=lambda: License.query, get_pk=lambda a: a.id, get_label=lambda a: a.name)
	tags         = QuerySelectMultipleField('Tags', query_factory=lambda: Tag.query, get_pk=lambda a: a.id, get_label=lambda a: a.title)
	repo         = StringField("Repo URL", [Optional(), URL()])
	website      = StringField("Website URL", [Optional(), URL()])
	issueTracker = StringField("Issue Tracker URL", [Optional(), URL()])
	forums	     = IntegerField("Forum Topic ID", [InputRequired(), NumberRange(0,999999)])
	submit	     = SubmitField("Save")

@menu.register_menu(app, ".new", "Create", order=21, visible_when=lambda: current_user.is_authenticated)
@app.route("/new/", methods=["GET", "POST"])
@app.route("/packages/<author>/<name>/edit/", methods=["GET", "POST"])
@login_required
def create_edit_package_page(author=None, name=None):
	package = None
	form = None
	if author is None:
		form = PackageForm(formdata=request.form)
		author = request.args.get("author")
		if author is None or author == current_user.username:
			author = current_user
		else:
			author = User.query.filter_by(username=author).first()
			if author is None:
				flash("Unable to find that user", "error")
				return redirect(url_for("create_edit_package_page"))

			if not author.checkPerm(current_user, Permission.CHANGE_AUTHOR):
				flash("Permission denied", "error")
				return redirect(url_for("create_edit_package_page"))

	else:
		package = getPackageByInfo(author, name)
		if not package.checkPerm(current_user, Permission.EDIT_PACKAGE):
			return redirect(package.getDetailsURL())

		author = package.author

		form = PackageForm(formdata=request.form, obj=package)

	# Initial form class from post data and default data
	if request.method == "POST" and form.validate():
		# Successfully submitted!
		if not package:
			package = Package()
			package.author = author
		else:
			triggerNotif(package.author, current_user,
					"{} edited".format(package.title), package.getDetailsURL())

		form.populate_obj(package) # copy to row

		package.tags.clear()
		for tag in form.tags.raw_data:
			package.tags.append(Tag.query.get(tag))

		db.session.commit() # save
		return redirect(package.getDetailsURL()) # redirect

	return render_template("packages/create_edit.html", package=package, form=form, author=author)

@app.route("/packages/<author>/<name>/approve/", methods=["POST"])
@login_required
@is_package_page
def approve_package_page(package):
	if not package.checkPerm(current_user, Permission.APPROVE_NEW):
		flash("You don't have permission to do that.", "error")

	elif package.approved:
		flash("Package has already been approved", "error")

	else:
		package.approved = True

		triggerNotif(package.author, current_user,
				"{} approved".format(package.title), package.getDetailsURL())
		db.session.commit()

	return redirect(package.getDetailsURL())

class CreateScreenshotForm(FlaskForm):
	title	   = StringField("Title/Caption", [Optional()])
	fileUpload = FileField("File Upload", [InputRequired()])
	submit	   = SubmitField("Save")

@app.route("/packages/<author>/<name>/screenshots/new/", methods=["GET", "POST"])
@login_required
@is_package_page
def create_screenshot_page(package):
	if not package.checkPerm(current_user, Permission.MAKE_RELEASE):
		return redirect(package.getDetailsURL())

	# Initial form class from post data and default data
	form = CreateScreenshotForm()
	if request.method == "POST" and form.validate():
		uploadedPath = doFileUpload(form.fileUpload.data, ["png", "jpg", "jpeg"],
				"a PNG or JPG image file")
		if uploadedPath is not None:
			ss = PackageScreenshot()
			ss.package = package
			ss.title   = form["title"].data
			ss.url     = uploadedPath
			db.session.add(ss)

			msg = "{}: Screenshot added {}" \
					.format(package.title, ss.title)
			triggerNotif(package.author, current_user, msg, erequest.getURL())
			db.session.commit()
			return redirect(package.getDetailsURL())

	return render_template("packages/screenshot_new.html", package=package, form=form)


class EditRequestForm(PackageForm):
	edit_title = StringField("Edit Title", [InputRequired(), Length(1, 100)])
	edit_desc  = TextField("Edit Description", [Optional()])

@app.route("/packages/<author>/<name>/requests/new/", methods=["GET","POST"])
@app.route("/packages/<author>/<name>/requests/<id>/edit/", methods=["GET","POST"])
@login_required
@is_package_page
def create_edit_editrequest_page(package, id=None):
	edited_package = package

	erequest = None
	if id is not None:
		erequest = EditRequest.query.get(id)
		if erequest.package != package:
			abort(404)

		from copy import copy
		edited_package = copy(package)
		erequest.applyAll(edited_package)

		if not erequest.checkPerm(current_user, Permission.EDIT_EDITREQUEST):
			abort(403)

		if erequest.status != 0:
			flash("Can't edit EditRequest, it has already been merged or rejected", "error")
			return redirect(erequest.getURL())


	form = EditRequestForm(request.form, obj=edited_package)
	if request.method == "POST" and form.validate():
		if erequest is None:
			erequest = EditRequest()
			erequest.package = package
			erequest.author  = current_user

		erequest.title   = form["edit_title"].data
		erequest.desc    = form["edit_desc"].data
		db.session.add(erequest)

		EditRequestChange.query.filter_by(request=erequest).delete()

		wasChangeMade = False
		for e in PackagePropertyKey:
			newValue = form[e.name].data
			oldValue = getattr(package, e.name)

			newValueComp = newValue
			oldValueComp = oldValue
			if type(newValue) is str:
				newValue = newValue.replace("\r\n", "\n")
				newValueComp = newValue.strip()
				oldValueComp = "" if oldValue is None else oldValue.strip()

			if newValueComp != oldValueComp:
				change = EditRequestChange()
				change.request = erequest
				change.key = e
				change.oldValue = e.convert(oldValue)
				change.newValue = e.convert(newValue)
				db.session.add(change)
				wasChangeMade = True

		if wasChangeMade:
			msg = "{}: Edit request #{} {}" \
					.format(package.title, erequest.id, "created" if id is None else "edited")
			triggerNotif(package.author, current_user, msg, erequest.getURL())
			triggerNotif(erequest.author, current_user, msg, erequest.getURL())
			db.session.commit()
			return redirect(erequest.getURL())
		else:
			flash("No changes detected", "warning")
	elif erequest is not None:
		form["edit_title"].data = erequest.title
		form["edit_desc"].data  = erequest.desc

	return render_template("packages/editrequest_create_edit.html", package=package, form=form)


@app.route("/packages/<author>/<name>/requests/<id>/")
@is_package_page
def view_editrequest_page(package, id):
	erequest = EditRequest.query.get(id)
	if erequest is None or erequest.package != package:
		abort(404)

	clearNotifications(erequest.getURL())
	return render_template("packages/editrequest_view.html", package=package, request=erequest)


@app.route("/packages/<author>/<name>/requests/<id>/approve/", methods=["POST"])
@is_package_page
def approve_editrequest_page(package, id):
	if not package.checkPerm(current_user, Permission.APPROVE_CHANGES):
		flash("You don't have permission to do that.", "error")
		return redirect(package.getDetailsURL())

	erequest = EditRequest.query.get(id)
	if erequest is None or erequest.package != package:
		abort(404)

	if erequest.status != 0:
		flash("Edit request has already been resolved", "error")

	else:
		erequest.status = 1
		erequest.applyAll(package)

		msg = "{}: Edit request #{} merged".format(package.title, erequest.id)
		triggerNotif(erequest.author, current_user, msg, erequest.getURL())
		triggerNotif(package.author, current_user, msg, erequest.getURL())
		db.session.commit()

	return redirect(package.getDetailsURL())

@app.route("/packages/<author>/<name>/requests/<id>/reject/", methods=["POST"])
@is_package_page
def reject_editrequest_page(package, id):
	if not package.checkPerm(current_user, Permission.APPROVE_CHANGES):
		flash("You don't have permission to do that.", "error")
		return redirect(package.getDetailsURL())

	erequest = EditRequest.query.get(id)
	if erequest is None or erequest.package != package:
		abort(404)

	if erequest.status != 0:
		flash("Edit request has already been resolved", "error")

	else:
		erequest.status = 2

		msg = "{}: Edit request #{} rejected".format(package.title, erequest.id)
		triggerNotif(erequest.author, current_user, msg, erequest.getURL())
		triggerNotif(package.author, current_user, msg, erequest.getURL())
		db.session.commit()

	return redirect(package.getDetailsURL())


class CreatePackageReleaseForm(FlaskForm):
	name	   = StringField("Name")
	title	   = StringField("Title")
	uploadOpt  = RadioField ("File", choices=[("vcs", "From VCS Commit or Branch"), ("upload", "File Upload")])
	vcsLabel   = StringField("VCS Commit or Branch", default="master")
	fileUpload = FileField("File Upload")
	submit	   = SubmitField("Save")

class EditPackageReleaseForm(FlaskForm):
	name     = StringField("Name")
	title    = StringField("Title")
	url      = StringField("URL", [URL])
	approved = BooleanField("Is Approved")
	submit   = SubmitField("Save")

@app.route("/packages/<author>/<name>/releases/new/", methods=["GET", "POST"])
@login_required
@is_package_page
def create_release_page(package):
	if not package.checkPerm(current_user, Permission.MAKE_RELEASE):
		return redirect(package.getDetailsURL())

	# Initial form class from post data and default data
	form = CreatePackageReleaseForm()
	if request.method == "POST" and form.validate():
		if form["uploadOpt"].data == "vcs":
			rel = PackageRelease()
			rel.package = package
			rel.title   = form["title"].data
			rel.url     = ""
			db.session.commit()

			rel.task_id = makeVCSRelease.delay(rel.id, form["vcsLabel"].data).id

			msg = "{}: Release {} created".format(package.title, rel.title)
			triggerNotif(package.author, current_user, msg, rel.getEditURL())
			db.session.commit()

			return redirect(url_for("check_task", id=rel.task_id, r=package.getDetailsURL()))
		else:
			uploadedPath = doFileUpload(form.fileUpload.data, ["zip"], "a zip file")
			if uploadedPath is not None:
				rel = PackageRelease()
				rel.package = package
				rel.title = form["title"].data
				rel.url = uploadedPath
				db.session.add(rel)

				msg = "{}: Release {} created".format(package.title, rel.title)
				triggerNotif(package.author, current_user, msg, erequest.getURL())
				db.session.commit()
				return redirect(package.getDetailsURL())

	return render_template("packages/release_new.html", package=package, form=form)

@app.route("/packages/<author>/<name>/releases/<id>/", methods=["GET", "POST"])
@login_required
@is_package_page
def edit_release_page(package, id):
	user = User.query.filter_by(username=author).first()
	if user is None:
		abort(404)

	release = PackageRelease.query.get(id)
	if release is None:
		abort(404)

	package = release.package
	if package.name != name or package.author.username != author:
		abort(404)

	clearNotifications(release.getEditURL())

	canEdit	= package.checkPerm(current_user, Permission.MAKE_RELEASE)
	canApprove = package.checkPerm(current_user, Permission.APPROVE_RELEASE)
	if not (canEdit or canApprove):
		return redirect(package.getDetailsURL())

	if release.task_id is not None:
		return redirect(url_for("check_task", id=release.task_id, r=release.getEditURL()))

	# Initial form class from post data and default data
	form = EditPackageReleaseForm(formdata=request.form, obj=release)
	if request.method == "POST" and form.validate():
		wasApproved = release.approved
		if canEdit:
			release.title = form["title"].data

		if package.checkPerm(current_user, Permission.CHANGE_RELEASE_URL):
			release.url = form["url"].data

		if canApprove:
			release.approved = form["approved"].data
		else:
			release.approved = wasApproved

		db.session.commit()
		return redirect(package.getDetailsURL())

	return render_template("packages/release_edit.html", package=package, release=release, form=form)
