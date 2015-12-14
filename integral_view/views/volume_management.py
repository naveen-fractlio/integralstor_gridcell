import re

import django.http, django
from  django.contrib import auth
from django.conf import settings

import salt.client

import integralstor_gridcell
from integralstor_gridcell import volume_info, system_info, gluster_commands, gluster_batch, iscsi
import integralstor_common
from integralstor_common import command, audit

import integral_view
from integral_view.forms import volume_management_forms
from integral_view.utils import iv_logging


def volume_specific_op(request, operation, vol_name=None):
  """ Used to carry out various volume related operations which is specified in the operation parameter. 
  The volume to be operated on is specified in the vol_name parameter"""

  return_dict = {}
  try:
    if not operation:
      raise Exception("Operation not specified.")
  
    return_dict['op'] = operation
    form = None
  
    vil, err = volume_info.get_volume_info_all()
    if err:
      raise Exception(err)
    if not vil:
      if operation != "view_snapshots":
        raise Exception('Could not load volume information')

    si, err = system_info.load_system_config()
    if err:
      raise Exception(err)
    if not si:
      raise Exception('Could not load system information')
 
    if request.method == "GET":
  
      if operation in ["vol_start", "vol_delete"]:
        l = []
        for v in vil:
          if v["status"] != 1:
            l.append(v["name"])
        form = integral_view.forms.volume_management_forms.VolumeNameForm(vol_list = l)
        if not l:
          return_dict["no_vols"] = True
      elif operation in ["vol_stop", "expand_volume", "start_rebalance", "vol_quota"]:
        l = []
        for v in vil:
          if v["status"] == 1:
            l.append(v["name"])
        form = integral_view.forms.volume_management_forms.VolumeNameForm(vol_list = l)

        if not l:
          return_dict["no_vols"] = True
      elif operation == "vol_options":
        il, err = iscsi.load_iscsi_volumes_list(vil)
        if err:
          raise Exception(err)
        l = []
        for v in vil:
          #Ignore ISCSI volumes for this
          if il and v["name"] in il:
            continue
          l.append(v["name"])
        form = integral_view.forms.volume_management_forms.VolumeNameForm(vol_list = l)
        if not l:
          return_dict["no_vols"] = True
  
      elif operation == "create_volume_dir":
        l = []
        for v in vil:
          l.append(v["name"])
        if not l:
          return_dict["no_vols"] = True
        form = integral_view.forms.volume_management_forms.VolumeNameForm(vol_list = l)
        return_dict['form'] = form
        return django.shortcuts.render_to_response('create_volume_dir.html', return_dict, context_instance=django.template.context.RequestContext(request))  
      else:
        l = []
        for v in vil:
          l.append(v["name"])
        if not l:
          return_dict["no_vols"] = True
        form = integral_view.forms.volume_management_forms.VolumeNameForm(vol_list = l)
    else:
      # POST method processing
      op_conf_msg = {
        'vol_stop':'Stopping volume will make its data inaccessible. Do you want to continue?', 
        'vol_delete': 'Deleting volume will erase all information about the volume. Do you want to continue?',
      }
      if operation == "vol_start":
        l = []
        for v in vil:
          if v["status"] != 1:
            l.append(v["name"])
        form = integral_view.forms.volume_management_forms.VolumeNameForm(request.POST, vol_list = l)
      elif operation in ["vol_stop", "expand_volume", "start_rebalance", "vol_quota"]:
        l = []
        for v in vil:
          if v["status"] == 1:
            l.append(v["name"])
        form = integral_view.forms.volume_management_forms.VolumeNameForm(request.POST, vol_list = l)
  
      elif operation == "create_volume_dir":
        dir_name = request.POST["name"]
        vol_name = request.POST["vol"]
        path = request.POST["path"]
  
        vol_creation, err = gluster_commands.create_gluster_dir(vol_name,(path+dir_name),0777)
        if err:
          raise Exception(err)
        if vol_creation:
          return_dict["conf_message"] = "Directory Creation success in path %s for volume %s"%(path+dir_name,vol_name)
          #Reinitialize the form and render back it on the screen.
          l = []
          for v in vil:
            l.append(v["name"])
          if not l:
            return_dict["no_vols"] = True
          form = integral_view.forms.volume_management_forms.VolumeNameForm(vol_list = l)
          return_dict['form'] = form        
          
          return django.shortcuts.render_to_response('create_volume_dir.html', return_dict, context_instance=django.template.context.RequestContext(request))  
        else:
          return_dict["error"] = "Directory creation error %s. Please try again"%(path+dir_name)
          return django.shortcuts.render_to_response('logged_in_error.html', return_dict, context_instance = django.template.context.RequestContext(request))
      else:
        l = []
        for v in vil:
          l.append(v["name"])
        form = integral_view.forms.volume_management_forms.VolumeNameForm(request.POST, vol_list = l)
      if form.is_valid():
        cd = form.cleaned_data
        vol_name = cd['vol_name']
        return_dict['vol_name'] = vol_name
        if operation in ['vol_stop', 'vol_delete']:
          return_dict['op_conf_msg'] = op_conf_msg[operation]
          return django.shortcuts.render_to_response('volume_specific_op_conf.html', return_dict, context_instance=django.template.context.RequestContext(request))
        elif operation == 'vol_quota':
          init = {}
          init["vol_name"] = vol_name
          vd, err = volume_info.get_volume_info(None, vol_name)
          if err:
            raise Exception(err)
          if not vd:
            raise Exception('Could not retrieve the information for volume %s'%vol_name)
          enable_quota = True
          if "options" in vd :
            for o in vd["options"]:
              if "features.quota" == o["name"]:
                if o["value"] == "on":
                  init["set_quota"] = True
                  if "quotas" in vd and "/" in vd["quotas"]:
                    q = vd["quotas"]["/"]
                    match = re.search('([0-9.]+)([A-Za-z]+)', q["limit"])
                    if match:
                      r  = match.groups()
                      init["limit"] = r[0]
                      init["unit"] = r[1].upper()
          form = volume_management_forms.VolumeQuotaForm(initial=init)
          return_dict["form"] = form
          return django.shortcuts.render_to_response('edit_volume_quota.html', return_dict, context_instance=django.template.context.RequestContext(request))
        elif operation == 'view_snapshots':
          l, err = volume_info.get_snapshots(vol_name)
          if err:
            raise Exception(err)
          vd, err = volume_info.get_volume_info(vil, vol_name)
          if err:
            raise Exception(err)
          if not vd:
            raise Exception('Could not retrieve the information for volume %s'%vol_name)
          if vd["status"] == 1:
            return_dict["vol_started"] = True
          else:
            return_dict["vol_started"] = False
          return_dict["snapshots"] = l
          return_dict["vol_name"] = vol_name
          return django.shortcuts.render_to_response('view_snapshots.html', return_dict, context_instance=django.template.context.RequestContext(request))
        elif operation == "vol_options":
          vol_dict, err = volume_info.get_volume_info(vil, vol_name)
          if err:
            raise Exception(err)
          if not vol_dict:
            raise Exception('Could not retrieve the information for volume %s'%vol_name)
          d = {}
          #Set default values
          d["auth_allow"] = '*'
          d["auth_reject"] = 'NONE'
          d["readonly"] = False
          d["nfs_disable"] = False
          d['nfs_volume_access'] = 'read-write'
          d["vol_name"] = vol_name
  
          # Now fill in current values and pass to the form
          if "options" in vol_dict:
            for option in vol_dict["options"]:
              if option["name"] == "auth.allow": 
                d["auth_allow"] = option["value"]
              if option["name"] == "auth.reject": 
                d["auth_reject"] = option["value"]
              if option["name"] == "nfs.disable": 
                if option["value"] == "on":
                  d["nfs_disable"] = True
              if option["name"] == "nfs.volume-access": 
                d["nfs_volume_access"] = option["value"]
              if option["name"] == "features.read-only": 
                d["readonly"] = option["value"]
              if option["name"] == "features.worm": 
                d["enable_worm"] = option["value"]
          form = integral_view.forms.volume_management_forms.VolumeOptionsForm(initial=d)
          return_dict["form"] = form
          return django.shortcuts.render_to_response('volume_options_form.html', return_dict, context_instance=django.template.context.RequestContext(request))
        elif operation == 'start_rebalance':
          d, err = gluster_batch.create_rebalance_command_file(vol_name)
          if err:
            raise Exception(err)
          if not "error" in d:
            ret, err = audit.audit("vol_rebalance_start", "Scheduled volume rebalance start for volume %s"%vol_name, request.META["REMOTE_ADDR"])
            if err:
              raise Exception(err)
            return django.http.HttpResponseRedirect('/show/batch_start_conf/%s'%d["file_name"])
          else:
            return_dict["error"] = "Error initiating rebalance : %s"%d["error"]
            return django.shortcuts.render_to_response('logged_in_error.html', return_dict, context_instance = django.template.context.RequestContext(request))
  
        elif operation in ['vol_start', 'rotate_log', 'check_rebalance', 'stop_rebalance']:
          return django.http.HttpResponseRedirect('/perform_op/%s/%s'%(operation, vol_name))
  
        elif operation == 'expand_volume':
  
          for vol in vil:
            if vol_name == vol["name"]:
              break
          count = 0
          replicated = False
          repl_count = 0
  
          if "replicate" in vol["type"].lower():
            replica_count = int(vol["replica_count"])
            replicated = True
  
          d, err = gluster_commands.build_expand_volume_command(vol, si)
          if err:
            raise Exception(err)
          if "error" in d:
            return_dict["error"] = "Error expanding the volume : %s"%d["error"]
            return django.shortcuts.render_to_response('logged_in_error.html', return_dict, context_instance = django.template.context.RequestContext(request))
          iv_logging.debug("Expand volume node list %s for volume %s"%(d['node_list'], vol["name"]))
  
          return_dict['cmd'] = d['cmd']
          return_dict['node_list'] = d['node_list']
          return_dict['count'] = d['count']
          return_dict['dataset_list'] = d['dataset_list']
          return_dict['vol_name'] = vol["name"]
          if vol["type"] == "Replicate":
            return_dict['vol_type'] = "replicated"
          else:
            return_dict['vol_type'] = "distributed"
              
          return django.shortcuts.render_to_response('expand_volume_form.html', return_dict, context_instance=django.template.context.RequestContext(request))
    # form not valid or called using get so return same form
    return_dict['form'] = form
    if operation == "volume_status":
      return_dict['vil'] = vil
      return django.shortcuts.render_to_response('volume_specific_status.html', return_dict, context_instance=django.template.context.RequestContext(request))
    else:
      if operation == 'rotate_log':
        return_dict['base_template'] = 'volume_log_base.html'
      elif operation == 'view_snapshots':
        return_dict['base_template'] = 'snapshot_base.html'
      else:
        return_dict['base_template'] = 'volume_base.html'
      return django.shortcuts.render_to_response('volume_specific_op_form.html', return_dict, context_instance=django.template.context.RequestContext(request))
  except Exception, e:
    s = str(e)
    if "Another transaction is in progress".lower() in s.lower():
      return_dict["error"] = "An underlying storage operation has locked a volume so we are unable to process this request. Please try after a couple of seconds"
    else:
      return_dict["error"] = "An error occurred when processing your request : %s"%s
    return django.shortcuts.render_to_response("logged_in_error.html", return_dict, context_instance=django.template.context.RequestContext(request))


def create_snapshot(request):

  return_dict = {}
  try:
    vil, err = volume_info.get_volume_info_all()
    if err:
      raise Exception(err)
    if not vil:
      return_dict['no_volumes'] = True
      return django.shortcuts.render_to_response('create_snapshot.html', return_dict, context_instance = django.template.context.RequestContext(request))
    l = []
    for v in vil:
      l.append(v["name"])
    if request.method == "GET":
      form = integral_view.forms.volume_management_forms.CreateSnapshotForm(vol_list=l)
      return_dict["form"] = form
      return django.shortcuts.render_to_response('create_snapshot.html', return_dict, context_instance = django.template.context.RequestContext(request))
    else:
      form = integral_view.forms.volume_management_forms.CreateSnapshotForm(request.POST, vol_list=l)
      if not form.is_valid():
        return_dict["form"] = form
        return django.shortcuts.render_to_response('create_snapshot.html', return_dict, context_instance = django.template.context.RequestContext(request))
      cd = form.cleaned_data
      d, err  = gluster_commands.create_snapshot(cd)
      if err:
        raise Exception(err)
      if d and  ("op_status" in d) and d["op_status"]["op_ret"] == 0:
        #Success so audit the change
        ret, err = audit.audit("create_snapshot", d["display_command"], request.META["REMOTE_ADDR"])
        if err:
          raise Exception(err)
        return_dict["op"] = "Create snapshot"
        return_dict["conf"] = d["display_command"]
        return django.shortcuts.render_to_response('snapshot_op_result.html', return_dict, context_instance = django.template.context.RequestContext(request))
      else:
        err = "Error creating the snapshot : "
        #assert False
        if d:
          if "error_list" in d:
            err += " ".join(d["error_list"])
          if "op_status" in d and "op_errstr" in d["op_status"]:
            if d["op_status"]["op_errstr"]:
              err += d["op_status"]["op_errstr"]
        else:
          err += "The snapshot command did not return a result. Please try again."
      return_dict["error"] = err
      return django.shortcuts.render_to_response('logged_in_error.html', return_dict, context_instance = django.template.context.RequestContext(request))
  except Exception, e:
    s = str(e)
    if "Another transaction is in progress".lower() in s.lower():
      return_dict["error"] = "An underlying storage operation has locked a volume so we are unable to process this request. Please try after a couple of seconds"
    else:
      return_dict["error"] = "An error occurred when processing your request : %s"%s
    return django.shortcuts.render_to_response("logged_in_error.html", return_dict, context_instance=django.template.context.RequestContext(request))

def delete_snapshot(request):

  return_dict = {}
  try:
    if request.method == "GET":
      # Disallowed GET method so return error.
      return_dict["error"] = "Invalid request. Please use the menu options."
    else:
      # POST method processing
      if "snapshot_name" not in request.POST:
        return_dict["error"] = "Snapshot name not specified. Please use the menu options."
      elif "conf" not in request.POST:
        #Get a conf from the user before we proceed
        return_dict["snapshot_name"] = request.POST["snapshot_name"]
        template = "delete_snapshot_conf.html"
      else:
        #Got a conf from the user so proceed
        snapshot_name = request.POST["snapshot_name"]
        d, err = gluster_commands.delete_snapshot(snapshot_name)
        if err:
          raise Exception(err)
        if d:
          #assert False
          if "op_status" in d:
            if d["op_status"]["op_errno"] == 0:
              return_dict["conf"] = "Successfully deleted snapshot - %s"%snapshot_name
              return_dict["op"] = "Delete snapshot"
              audit_str = "Deleted snapshot %s."%snapshot_name
              ret, err = audit.audit("delete_snapshot", audit_str, request.META["REMOTE_ADDR"])
              if err:
                raise Exception(err)
              template = "snapshot_op_result.html"
            else:
              err = "Error deleting the snapshot :"
              if "op_status" in d and "op_errstr" in d["op_status"]:
                err += d["op_status"]["op_errstr"]
              if "error_list" in d:
                err += " ".join(d["error_list"])
              raise Exception(err)
          else:
            raise Exception("Could not detect the status of the snapshot deletion. Please try again.")
  
    return django.shortcuts.render_to_response(template, return_dict, context_instance = django.template.context.RequestContext(request))
  except Exception, e:
    s = str(e)
    if "Another transaction is in progress".lower() in s.lower():
      return_dict["error"] = "An underlying storage operation has locked a volume so we are unable to process this request. Please try after a couple of seconds"
    else:
      return_dict["error"] = "An error occurred when processing your request : %s"%s
    return django.shortcuts.render_to_response("logged_in_error.html", return_dict, context_instance=django.template.context.RequestContext(request))


def restore_snapshot(request):

  return_dict = {}
  try:
    form = None
    template = "logged_in_error.html"
  
    if request.method == "GET":
      # Disallowed GET method so return error.
      return_dict["error"] = "Invalid request. Please use the menu options."
    else:
      # POST method processing
      if "snapshot_name" not in request.POST:
        return_dict["error"] = "Snapshot name not specified. Please use the menu options."
      elif "conf" not in request.POST:
        #Get a conf from the user before we proceed
        return_dict["snapshot_name"] = request.POST["snapshot_name"]
        return_dict["vol_name"] = request.POST["vol_name"]
        template = "restore_snapshot_conf.html"
      else:
        #Got a conf from the user so proceed
        snapshot_name = request.POST["snapshot_name"]
        vol_name = request.POST["vol_name"]
        d, err = gluster_commands.restore_snapshot(snapshot_name)
        if err:
          raise Exception(err)
        if d:
          #assert False
          if "op_status" in d:
            if d["op_status"]["op_errno"] == 0:
              return_dict["conf"] = "Successfully restored snapshot %s onto volume %s"%(snapshot_name, vol_name)
              return_dict["op"] = "Restore snapshot"
              audit_str = "Restored snapshot %s onto volume %s."%(snapshot_name, vol_name)
              ret, err = audit.audit("restore_snapshot", audit_str, request.META["REMOTE_ADDR"])
              if err:
                raise Exception(err)
              template = "snapshot_op_result.html"
            else:
              err = "Error restoring the snapshot :"
              if "op_status" in d and "op_errstr" in d["op_status"]:
                err += d["op_status"]["op_errstr"]
              if "error_list" in d:
                err += " ".join(d["error_list"])
              raise Exception(err)
          else:
            raise Exception("Could not detect the status of the snapshot restoration. Please try again.")
  
    return django.shortcuts.render_to_response(template, return_dict, context_instance = django.template.context.RequestContext(request))
  except Exception, e:
    s = str(e)
    if "Another transaction is in progress".lower() in s.lower():
      return_dict["error"] = "An underlying storage operation has locked a volume so we are unable to process this request. Please try after a couple of seconds"
    else:
      return_dict["error"] = "An error occurred when processing your request : %s"%s
    return django.shortcuts.render_to_response("logged_in_error.html", return_dict, context_instance=django.template.context.RequestContext(request))

          
def deactivate_snapshot(request):

  return_dict = {}
  try:
    form = None
    template = "logged_in_error.html"
  
    if request.method == "GET":
      # Disallowed GET method so return error.
      raise Exception("Invalid request. Please use the menu options.")
    else:
      # POST method processing
      if "snapshot_name" not in request.POST:
        raise Exception("Snapshot name not specified. Please use the menu options.")
      elif "conf" not in request.POST:
        #Get a conf from the user before we proceed
        return_dict["snapshot_name"] = request.POST["snapshot_name"]
        template = "deactivate_snapshot_conf.html"
      else:
        #Got a conf from the user so proceed
        snapshot_name = request.POST["snapshot_name"]
        d, err = gluster_commands.deactivate_snapshot(snapshot_name)
        if err:
          raise Exception(err)
        if d:
          #assert False
          if "op_status" in d:
            if d["op_status"]["op_errno"] == 0:
              return_dict["conf"] = "Successfully deactivated snapshot - %s"%snapshot_name
              return_dict["op"] = "Deactivate snapshot"
              audit_str = "Deactivated snapshot %s."%snapshot_name
              ret, err = audit.audit("deactivate_snapshot", audit_str, request.META["REMOTE_ADDR"])
              if err:
                raise Exception(err)
              template = "snapshot_op_result.html"
            else:
              err = "Error deactivating the snapshot :"
              if "op_status" in d and "op_errstr" in d["op_status"]:
                err += d["op_status"]["op_errstr"]
              if "error_list" in d:
                err += " ".join(d["error_list"])
              raise Exception(err)
          else:
            raise Exception("Could not detect the status of the snapshot deactivation. Please try again.")
  
    return django.shortcuts.render_to_response(template, return_dict, context_instance = django.template.context.RequestContext(request))
  except Exception, e:
    s = str(e)
    if "Another transaction is in progress".lower() in s.lower():
      return_dict["error"] = "An underlying storage operation has locked a volume so we are unable to process this request. Please try after a couple of seconds"
    else:
      return_dict["error"] = "An error occurred when processing your request : %s"%s
    return django.shortcuts.render_to_response("logged_in_error.html", return_dict, context_instance=django.template.context.RequestContext(request))

def activate_snapshot(request):

  return_dict = {}
  try:
    form = None
    template = "logged_in_error.html"
  
    if request.method == "GET":
      # Disallowed GET method so return error.
      return_dict["error"] = "Invalid request. Please use the menu options."
    else:
      # POST method processing
      if "snapshot_name" not in request.POST:
        return_dict["error"] = "Snapshot name not specified. Please use the menu options."
      else:
        snapshot_name = request.POST["snapshot_name"]
        d, err = gluster_commands.activate_snapshot(snapshot_name)
        if err:
          raise Exception(err)
        if d:
          #assert False
          if "op_status" in d:
            if d["op_status"]["op_errno"] == 0:
              return_dict["conf"] = "Successfully activated snapshot - %s"%snapshot_name
              return_dict["op"] = "Activate snapshot"
              audit_str = "Activated snapshot %s."%snapshot_name
              ret, err = audit.audit("activate_snapshot", audit_str, request.META["REMOTE_ADDR"])
              if err:
                raise Exception(err)
              template = "snapshot_op_result.html"
            else:
              err = "Error activating the snapshot :"
              if "op_status" in d and "op_errstr" in d["op_status"]:
                err += d["op_status"]["op_errstr"]
              if "error_list" in d:
                err += " ".join(d["error_list"])
              raise Exception(err)
          else:
            raise Exception("Could not detect the status of the snapshot activation. Please try again.")
  
    return django.shortcuts.render_to_response(template, return_dict, context_instance = django.template.context.RequestContext(request))
  except Exception, e:
    s = str(e)
    if "Another transaction is in progress".lower() in s.lower():
      return_dict["error"] = "An underlying storage operation has locked a volume so we are unable to process this request. Please try after a couple of seconds"
    else:
      return_dict["error"] = "An error occurred when processing your request : %s"%s
    return django.shortcuts.render_to_response("logged_in_error.html", return_dict, context_instance=django.template.context.RequestContext(request))


  
def set_volume_options(request):

  return_dict = {}
  try:
    if request.method == "GET":
      # Disallowed GET method so return error.
      raise Exception("Invalid request. Please use the menu options.")
    form = integral_view.forms.volume_management_forms.VolumeOptionsForm(request.POST)
  
    if not form.is_valid():
      return_dict["form"] = form
      return django.shortcuts.render_to_response('volume_options_form.html', return_dict, context_instance = django.template.context.RequestContext(request))
    cd = form.cleaned_data
    ol, err = volume_info.set_volume_options(cd)
    if err:
      raise Exception(err)
    if ol:
      for d in ol:
        if d and ("op_status" in d) and d["op_status"]["op_ret"] == 0:
          #Success so audit the change
          ret, err = audit.audit("set_vol_options", d["display_command"], request.META["REMOTE_ADDR"])
          if err:
            raise Exception(err)
  
    return_dict["result_list"] = ol
    return django.shortcuts.render_to_response('volume_options_result.html', return_dict, context_instance = django.template.context.RequestContext(request))
  except Exception, e:
    s = str(e)
    if "Another transaction is in progress".lower() in s.lower():
      return_dict["error"] = "An underlying storage operation has locked a volume so we are unable to process this request. Please try after a couple of seconds"
    else:
      return_dict["error"] = "An error occurred when processing your request : %s"%s
    return django.shortcuts.render_to_response("logged_in_error.html", return_dict, context_instance=django.template.context.RequestContext(request))


def set_volume_quota(request):
  return_dict = {}
  try:
    if request.method == "GET":
      # Disallowed GET method so return error.
      raise Exception("Invalid request. Please use the menu options.")
  
    form = integral_view.forms.volume_management_forms.VolumeQuotaForm(request.POST)
  
    if not form.is_valid():
      return_dict["form"] = form
      return django.shortcuts.render_to_response('edit_volume_quota.html', return_dict, context_instance = django.template.context.RequestContext(request))
    cd = form.cleaned_data
    vol_name = cd["vol_name"]
    vd, err = volume_info.get_volume_info(None, vol_name)
    if err:
      raise Exception(err)
    enable_quota = True
    if "options" in vd :
      for o in vd["options"]:
        if o["name"] == "features.quota" and o["value"] == "on":
          enable_quota = False
          break
    ol, err = gluster_commands.set_volume_quota(cd["vol_name"], enable_quota, cd["set_quota"], cd["limit"], cd["unit"])
    if err:
      raise Exception(err)
    if ol:
      for d in ol:
        if d and ("op_status" in d) and d["op_status"]["op_ret"] == 0:
          #Success so audit the change
          ret, err = audit.audit("set_vol_quota", d["display_command"], request.META["REMOTE_ADDR"])
          if err:
            raise Exception(err)
  
    return_dict["result_list"] = ol
    return_dict["app_debug"] = settings.APP_DEBUG
    return django.shortcuts.render_to_response('volume_quota_result.html', return_dict, context_instance = django.template.context.RequestContext(request))
  except Exception, e:
    s = str(e)
    if "Another transaction is in progress".lower() in s.lower():
      return_dict["error"] = "An underlying storage operation has locked a volume so we are unable to process this request. Please try after a couple of seconds"
    else:
      return_dict["error"] = "An error occurred when processing your request : %s"%s
    return django.shortcuts.render_to_response("logged_in_error.html", return_dict, context_instance=django.template.context.RequestContext(request))

  
def delete_volume(request):

  return_dict = {}
  try:
    form = None
  
    vil, err = volume_info.get_volume_info_all()
    if err:
      raise Exception(err)
    if not vil:
      raise Exception('Could not load volume information')
    si, err = system_info.load_system_config()
    if err:
      raise Exception(err)
    if not si:
      raise Exception('Could not load system information')

    return_dict['system_config_list'] = si
  
    if request.method == "GET":
      raise Exception("Invalid access. Please use the menus to perform functions.")
    else:
      if "vol_name" not in request.POST:
        raise Exception("Volume not specified. Please use the menus to perform functions.")
      vol_name = request.POST["vol_name"]
      v, err = volume_info.get_volume_info(vil, vol_name)
      if err:
        raise Exception(err)
      if not v:
        raise Exception('Could not load volume information')
      #assert False
      result_list = []
      d = {}
      cmd = 'gluster --mode=script volume delete %s '%vol_name
      d["command"] = "Deleting volume %s"%vol_name
      d["actual_command"] = cmd
      (r, rc), err = command.execute_with_rc(cmd)
      if err:
        raise Exception(err)
      if rc == 0:
        ret, err = audit.audit("vol_delete", "Deleted volume %s"%(vol_name), request.META["REMOTE_ADDR"])
        if err:
          raise Exception(err)
        # Now delete the brick directories
        d["result"] = "Success"
        result_list.append(d)
        for bricks in  v["bricks"]:
          for b in bricks:
            d = {}
            l = b.split(':')
            d["command"] = "Deleting volume storage on GRIDCell %s"%l[0]
            #print "executing command"
            client = salt.client.LocalClient()
            cmd_to_run = 'zfs destroy %s'%l[1][1:]
            #print 'Running %s'%cmd_to_run
            #assert False
            rc = client.cmd(l[0], 'cmd.run_all', [cmd_to_run])
            if rc:
              for hostname, res in rc.items():
                #print ret
                if res["retcode"] != 0:
                  errors = "Error destroying the brick path ZFS dataset on %s"%hostname
                  d["result"] = "Failed with error : %s"%errors
                else:
                  d["result"] = "Success"
                result_list.append(d)
 
      else:
        el, err = command.get_error_list(r)
        if err:
          raise Exception(err)
        ol, err = command.get_output_list(r)
        if err:
          raise Exception(err)
        estr = ""
        if el:
          estr = " , ".join(el)
        if ol:
          estr += " , ".join(ol)
        d["result"] = "Failed with error : %s"%estr
        result_list.append(d)
  
      return_dict["result_list"] = result_list
      return_dict["app_debug"] = settings.APP_DEBUG
      return django.shortcuts.render_to_response('volume_delete_results.html', return_dict, context_instance = django.template.context.RequestContext(request))
  except Exception, e:
    s = str(e)
    if "Another transaction is in progress".lower() in s.lower():
      return_dict["error"] = "An underlying storage operation has locked a volume so we are unable to process this request. Please try after a couple of seconds"
    else:
      return_dict["error"] = "An error occurred when processing your request : %s"%s
    return django.shortcuts.render_to_response("logged_in_error.html", return_dict, context_instance=django.template.context.RequestContext(request))


def replace_node(request):

  return_dict = {}
  try:
    form = None
  
    vil, err = volume_info.get_volume_info_all()
    if err:
      raise Exception(err)
    if not vil:
      raise Exception('Could not load volume information')
    si, err = system_info.load_system_config()
    if err:
      raise Exception(err)
    if not si:
      raise Exception('Could not load system information')
    return_dict['system_config_list'] = si
  
    
    d, err = system_info.get_replacement_node_info(si, vil)
    if err:
      raise Exception(err)
    if not d:
      raise Exception('Could not load replacement GRIDCell information')
      
    if not d["src_node_list"]:
      return_dict["error"] = "There are no GRIDCells eligible to be replaced."
      return django.shortcuts.render_to_response('logged_in_error.html', return_dict, context_instance = django.template.context.RequestContext(request))
    if not d["dest_node_list"]:
      return_dict["error"] = "There are no eligible replacement GRIDCells."
      return django.shortcuts.render_to_response('logged_in_error.html', return_dict, context_instance = django.template.context.RequestContext(request))
  
    return_dict["src_node_list"] = d["src_node_list"]
    return_dict["dest_node_list"] = d["dest_node_list"]
    #assert False
  
    if request.method == "GET":
      form = volume_management_forms.ReplaceNodeForm(d["src_node_list"], d["dest_node_list"])
      return_dict["form"] = form
      return_dict["supress_error_messages"] = True
      #print "form errors ----->"
      #print form.errors
      return django.shortcuts.render_to_response('replace_node_choose_node.html', return_dict, context_instance=django.template.context.RequestContext(request))
    else:
      if "conf" in request.POST:
        form = volume_management_forms.ReplaceNodeConfForm(request.POST)
        if form.is_valid():
          cd = form.cleaned_data
  
          src_node = cd["src_node"]
          dest_node = cd["dest_node"]
  
          vol_list, err = get_volumes_on_node(src_node, vil)
          if err:
            raise Exception(err)
          client = salt.client.LocalClient()
          revert_list = []
          if vol_list:
            for vol in vol_list:
              #Get the brick path and the data set name
              if 'bricks' in vol and vol['bricks']:
                brick1 = vol['bricks'][0]
                d, err = volume_info.get_components(brick1)
                if err:
                  raise Exception(err)
                if not d:
                  raise Exception("Error decoding the brick for the specified volume. Brick name : %s "%brick1)

                dataset_cmd = 'zfs create %s/%s/%s'%(d['pool'], d['ondisk_storage'], vol.strip())
                revert_cmd = 'zfs destroy %s/%s/%s'%(d['pool'], d['ondisk_storage'], vol.strip())
                r1 = client.cmd(dest_node, 'cmd.run_all', [dataset_cmd])
                if r1:
                  for node, ret in r1.items():
                    #print ret
                   if ret["retcode"] != 0:
                      errors += ", Error creating the underlying storage brick on %s"%node
                      print errors
                   else:
                      revert_list.append(revert_cmd)
  
              else:
                raise Exception("No bricks found for the specified volume ")

          #What do we do with this revert list?!
          d, err = gluster_batch.create_replace_command_file(si, vil, src_node, dest_node)
          if err:
            raise Exception(err)
          if "error" in d:
            if revert_list:
              #Undo the creation of the datasets
              for dsr_cmd in revert_list:
                  r1 = client.cmd(dest_node, 'cmd.run_all', [dsr_cmd])
                  if r1:
                    for node, ret in r1.items():
                      #print ret
                      if ret["retcode"] != 0:
                        errors += " , Error undoing the creation of the underlying storage brick on %s"%dest_node
                        d["error"].append(errors)
            raise Exception("Error initiating replace : %s"%d["error"])
            return django.shortcuts.render_to_response('logged_in_error.html', return_dict, context_instance = django.template.context.RequestContext(request))
          else:
            ret, err = audit.audit("replace_node", "Scheduled replacement of GRIDCell %s with GRIDCell %s"%(src_node, dest_node), request.META["REMOTE_ADDR"])
            if err:
              raise Exception(err)
            return django.http.HttpResponseRedirect('/show/batch_start_conf/%s'%d["file_name"])
      else:
        form = volume_management_forms.ReplaceNodeForm(request.POST, src_node_list = d["src_node_list"], dest_node_list = d["dest_node_list"])
        if form.is_valid():
          cd = form.cleaned_data
          src_node = cd["src_node"]
          dest_node = cd["dest_node"]
          return_dict["src_node"] = src_node
          return_dict["dest_node"] = dest_node
          return django.shortcuts.render_to_response('replace_node_conf.html', return_dict, context_instance=django.template.context.RequestContext(request))
        else:
          return_dict["form"] = form
          return django.shortcuts.render_to_response('replace_node_choose_node.html', return_dict, context_instance=django.template.context.RequestContext(request))
  except Exception, e:
    s = str(e)
    if "Another transaction is in progress".lower() in s.lower():
      return_dict["error"] = "An underlying storage operation has locked a volume so we are unable to process this request. Please try after a couple of seconds"
    else:
      return_dict["error"] = "An error occurred when processing your request : %s"%s
    return django.shortcuts.render_to_response("logged_in_error.html", return_dict, context_instance=django.template.context.RequestContext(request))



def replace_disk(request):

  return_dict = {}
  try:
    form = None
  
    vil, err = volume_info.get_volume_info_all()
    if err:
      raise Exception(err)
    if not vil:
      raise Exception('Could not load volume information')
    si, err = system_info.load_system_config()
    if err:
      raise Exception(err)
    if not si:
      raise Exception('Could not load system information')
    return_dict['system_config_list'] = si
    
    template = 'logged_in_error.html'
  
    python_scripts_path, err = common.get_python_scripts_path()
    if err:
      raise Exception(err)
    common_python_scripts_path, err = common.get_common_python_scripts_path()
    if err:
      raise Exception(err)
    if request.method == "GET":
      raise Exception("Incorrect access method. Please use the menus")
    else:
      node = request.POST["node"]
      serial_number = request.POST["serial_number"]
  
      if "conf" in request.POST:
        if "node" not in request.POST or  "serial_number" not in request.POST:
          return_dict["error"] = "Incorrect access method. Please use the menus"
        elif request.POST["node"] not in si:
          return_dict["error"] = "Unknown GRIDCell. Please use the menus"
        elif "step" not in request.POST :
          return_dict["error"] = "Incomplete request. Please use the menus"
        elif request.POST["step"] not in ["offline_disk", "scan_for_new_disk", "online_new_disk"]:
          return_dict["error"] = "Incomplete request. Please use the menus"
        else:
          step = request.POST["step"]
  
          # Which step of the replace disk are we in?
  
          if step == "offline_disk":
  
            #get the pool corresponding to the disk
            #zpool offline pool disk
            #send a screen asking them to replace the disk
  
            pool = None
            if serial_number in si[node]["disks"]:
              disk = si[node]["disks"][serial_number]
              if "pool" in disk:
                pool = disk["pool"]
              disk_id = disk["id"]
            if not pool:
              raise Exception("Could not find the storage pool on that disk. Please use the menus")
            else:
              '''
              pid = -1
              #Got the pool so now find the brick pid corresponding to the pool.
              for vol in vil:
                if "brick_status" not in vol:
                  continue
                bs = vol["brick_status"]
                for brick_name, brick_status_dict in bs.items():
                  if node in brick_name: 
                    path = brick_status_dict["path"]
                    r = re.search('/%s/[\S]+'%pool, path)
                    if r:
                      pid = brick_status_dict['pid']
                      break
                if pid != -1:
                  break
              if pid != -1:
              #issue the kill to the process here, using salt
              '''
  
              #issue a zpool offline pool disk-id using salt
              client = salt.client.LocalClient()
              cmd_to_run = 'zpool offline %s %s'%(pool, disk_id)
              #print 'Running %s'%cmd_to_run
              #assert False
              rc = client.cmd(node, 'cmd.run_all', [cmd_to_run])
              if rc:
                for node, ret in rc.items():
                  #print ret
                  if ret["retcode"] != 0:
                    error = "Error bringing the disk with serial number %s offline on %s : "%(serial_number, node)
                    if "stderr" in ret:
                      error += ret["stderr"]
                    return_dict["error"] = error
                    return django.shortcuts.render_to_response('logged_in_error.html', return_dict, context_instance = django.template.context.RequestContext(request))
              #print rc
              #if disk_status == "Disk Missing":
              #  #Issue a reboot now, wait for a couple of seconds for it to shutdown and then redirect to the template to wait for reboot..
              #  pass
              return_dict["serial_number"] = serial_number
              return_dict["node"] = node
              return_dict["pool"] = pool
              return_dict["old_id"] = disk_id
              template = "replace_disk_prompt.html"
  
          elif step == "scan_for_new_disk":
  
            #they have replaced the disk so scan for the new disk
            # and prompt for a confirmation of the new disk serial number
  
            pool = request.POST["pool"]
            old_id = request.POST["old_id"]
            return_dict["node"] = node
            return_dict["serial_number"] = serial_number
            return_dict["pool"] = pool
            return_dict["old_id"] = old_id
            old_disks = si[node]["disks"].keys()
            client = salt.client.LocalClient()
            rc = client.cmd(node, 'integralstor.disk_info_and_status')
            if rc and node in rc:
              new_disks = rc[node].keys()
              if new_disks:
                for disk in new_disks:
                  if disk not in old_disks:
                    return_dict["inserted_disk_serial_number"] = disk
                    return_dict["new_id"] = rc[node][disk]["id"]
                    break
                if "inserted_disk_serial_number" not in return_dict:
                  raise Exception("Could not detect any new disk.")
                else:
                  template = "replace_disk_confirm_new_disk.html"
  
  
          elif step == "online_new_disk":
  
            #they have confirmed the new disk serial number
            #get the id of the disk and
            #zpool replace poolname old disk new disk
            #zpool clear poolname to clear old errors
            #return a result screen
            pool = request.POST["pool"]
            old_id = request.POST["old_id"]
            new_id = request.POST["new_id"]
            new_serial_number = request.POST["new_serial_number"]
            cmd_to_run = "zpool replace -f %s %s %s"%(pool, old_id, new_id)
            #print 'Running %s'%cmd_to_run
            client = salt.client.LocalClient()
            rc = client.cmd(node, 'cmd.run_all', [cmd_to_run])
            if rc:
              #print rc
              for node, ret in rc.items():
                #print ret
                if ret["retcode"] != 0:
                  error = "Error replacing the disk on %s : "%(node)
                  if "stderr" in ret:
                    error += ret["stderr"]
                  rc = client.cmd(node, 'cmd.run', ['zpool online %s %s'%(pool, old_id)])
                  raise Exception(error)
            else:
              raise Exception("Error replacing the disk on %s : "%(node))

            '''
            cmd_to_run = "zpool set autoexpand=on %s"%pool
            print 'Running %s'%cmd_to_run
            rc = client.cmd(node, 'cmd.run_all', [cmd_to_run])
            if rc:
              for node, ret in rc.items():
                #print ret
                if ret["retcode"] != 0:
                  error = "Error setting pool autoexpand on %s : "%(node)
                  if "stderr" in ret:
                    error += ret["stderr"]
                  return_dict["error"] = error
                  return django.shortcuts.render_to_response('logged_in_error.html', return_dict, context_instance = django.template.context.RequestContext(request))
            print rc
            if new_serial_number in si[node]["disks"]:
              disk = si[node]["disks"][new_serial_number]
              disk_id = disk["id"]
            '''
            cmd_to_run = 'zpool online %s %s'%(pool, new_id)
            #print 'Running %s'%cmd_to_run
            rc = client.cmd(node, 'cmd.run_all', [cmd_to_run])
            if rc:
              #print rc
              for node, ret in rc.items():
                #print ret
                if ret["retcode"] != 0:
                  error = "Error bringing the new disk online on %s : "%(node)
                  if "stderr" in ret:
                    error += ret["stderr"]
                  raise Exception(error)
            else:
              raise Exception("Error bringing the new disk online on %s : "%(node))
            (ret, rc), err = command.execute_with_rc('%s/generate_manifest.py'%common_python_scripts_path)
            if err:
              raise Exception(err)
            #print ret
            if rc != 0:
              #print ret
              raise Exception("Could not regenrate the new hardware configuration. Error generating manifest. Return code %d"%rc)
            else:
              (ret, rc), err = command.execute_with_rc('%s/generate_status.py'%common_python_scripts_path)
              if err:
                raise Exception(err)
              if rc != 0:
                #print ret
                raise Exception("Could not regenrate the new hardware configuration. Error generating status. Return code %d"%rc)
              si, err = system_info.load_system_config()
              if err:
                raise Exception(err)
              return_dict["node"] = node
              return_dict["old_serial_number"] = serial_number
              return_dict["new_serial_number"] = new_serial_number
              template = "replace_disk_success.html"
  
          return django.shortcuts.render_to_response(template, return_dict, context_instance = django.template.context.RequestContext(request))
          
      else:
        if "node" not in request.POST or  "serial_number" not in request.POST:
          raise Exception("Incorrect access method. Please use the menus")
        else:
          return_dict["node"] = request.POST["node"]
          return_dict["serial_number"] = request.POST["serial_number"]
          template = "replace_disk_conf.html"
    return django.shortcuts.render_to_response(template, return_dict, context_instance=django.template.context.RequestContext(request))
  except Exception, e:
    s = str(e)
    if "Another transaction is in progress".lower() in s.lower():
      return_dict["error"] = "An underlying storage operation has locked a volume so we are unable to process this request. Please try after a couple of seconds"
    else:
      return_dict["error"] = "An error occurred when processing your request : %s"%s
    return django.shortcuts.render_to_response("logged_in_error.html", return_dict, context_instance=django.template.context.RequestContext(request))

  
    
def expand_volume(request):

  return_dict = {}
  try:
    form = None
  
    vil, err = volume_info.get_volume_info_all()
    if err:
      raise Exception(err)
    if not vil:
      raise Exception('Could not load volume information')
  
    if request.method == "GET":
      # Disallowed GET method so return error.
      raise Exception("Invalid request. Please use the menu options.")
    else:
      # POST method processing
  
      if "cmd" not in request.POST or "vol_name" not in request.POST or "count" not in request.POST:
        raise Exception("Invalid request. Please use the menu options.")
  
      cmd = request.POST['cmd']
      dsl = request.POST.getlist('dataset_list')
      dataset_dict = {}
      for ds in dsl:
        tl = ds.split(':')
        dataset_dict[tl[0]] = tl[1]
      vol_name = request.POST['vol_name']
      count = request.POST['count']
      #First create the datasets on which the bricks will reside
      client = salt.client.LocalClient()
      revert_list = []
      errors = ""
      for node, dataset in dataset_dict.items():
        dataset_cmd = 'zfs create %s'%dataset
        dataset_revert_cmd = 'zfs destory %s'%dataset
        r1 = client.cmd(node, 'cmd.run_all', [dataset_cmd])
        if r1:
          for node, ret in r1.items():
            #print ret
            if ret["retcode"] != 0:
              errors += ", Error creating the underlying storage brick on %s"%node
              print errors
            else:
              revert_list.append({node:dataset_revert_cmd})
  
      if errors != "":
        if revert_list:
          #Undo the creation of the datasets
          for revert in revert_list:
            for node, dsr_cmd in revert.items():
              r1 = client.cmd(node, 'cmd.run_all', [dsr_cmd])
              if r1:
                for node, ret in r1.items():
                  #print ret
                  if ret["retcode"] != 0:
                    errors += ", Error undoing the creating the underlying storage brick on %s"%node
        raise Exception(errors)
  
  
      iv_logging.info("Running volume expand : %s"%cmd)
      devel_files_path, err = common.get_devel_files_path()
      d, err = gluster_commands.run_gluster_command(cmd, "%s/add_brick.xml"%devel_files_path, "Volume expansion")
      if err:
        raise Exception(err)
  
      if d and ("op_status" in d) and d["op_status"]["op_ret"] == 0:
        #Success so audit the change
        audit_str = "Expanded volume %s by adding %s storage units."%(vol_name, count)
        ret, err = audit.audit("expand_volume", audit_str, request.META["REMOTE_ADDR"])
        if err:
          raise Exception(err)
      else:
        if revert_list:
          #Undo the creation of the datasets
          for revert in revert_list:
            for node, dsr_cmd in revert.items():
              r1 = client.cmd(node, 'cmd.run_all', [dsr_cmd])
              if r1:
                for node, ret in r1.items():
                  #print ret
                  if ret["retcode"] != 0:
                    errors += ", Error undoing the creating the underlying storage brick on %s"%node
  
      if d:
        d["command"] = "Volume expansion of %s by adding %s storage units."%(vol_name, count)
  
      return_dict['result_dict'] = d 
      if settings.APP_DEBUG:
        return_dict['app_debug'] = True 
  
      return_dict['base_template'] = 'volume_base.html'
      return django.shortcuts.render_to_response('render_op_xml_results.html', return_dict, context_instance = django.template.context.RequestContext(request))
  except Exception, e:
    s = str(e)
    if "Another transaction is in progress".lower() in s.lower():
      return_dict["error"] = "An underlying storage operation has locked a volume so we are unable to process this request. Please try after a couple of seconds"
    else:
      return_dict["error"] = "An error occurred when processing your request : %s"%s
    return django.shortcuts.render_to_response("logged_in_error.html", return_dict, context_instance=django.template.context.RequestContext(request))


