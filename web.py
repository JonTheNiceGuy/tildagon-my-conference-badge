"""Web server functionality for Conference Badge app."""

import os
import socket
import network
import settings

from .helpers import (
    KEY_DISPLAY_FIELDS, KEY_NAME, KEY_ICE_PHONE, KEY_ICE_NAME, KEY_ICE_NOTES,
    IMAGE_FIELD, EMF_LOGO_FIELD, COLOUR_NAMES,
    display_name, verb_key, field_key, generate_token, format_exception,
    parse_form, html_esc
)


def _generate_port():
    """Generate a random port between 3000 and 3999."""
    try:
        raw = os.urandom(2)
        value = (raw[0] << 8) | raw[1]
        return 3000 + (value % 1000)
    except Exception:
        import random
        return random.randint(3000, 3999)

try:
    from .qr import encode as qr_encode
except ImportError:
    from qr import encode as qr_encode


class WebServerMixin:
    """Mixin class providing web server functionality for badge configuration."""

    def _start_web_server(self):
        """Start the web server and generate QR code."""
        self.session_token = generate_token()

        wlan = network.WLAN(network.STA_IF)
        if not wlan.isconnected():
            return False

        self.ip_address = wlan.ifconfig()[0]
        self.port = _generate_port()
        self.server_url = "http://" + self.ip_address + ":" + str(self.port) + "/" + self.session_token

        try:
            self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.server_socket.bind(('0.0.0.0', self.port))
            self.server_socket.listen(1)
            self.server_socket.setblocking(False)
        except Exception as e:
            print("Server start error: " + str(e))
            return False

        # Generate QR code
        try:
            self.qr_matrix = qr_encode(self.server_url)
        except Exception as e:
            print("QR encode error: " + str(e))

        self.mode = self.MODE_WEB_SERVER
        return True

    def _stop_web_server(self):
        """Stop the web server."""
        if self.server_socket:
            try:
                self.server_socket.close()
            except:
                pass
            self.server_socket = None
        self.mode = self.MODE_BADGE
        self.qr_matrix = None
        self._load_settings()

    def _poll_server(self):
        """Check for incoming HTTP requests (non-blocking)."""
        if not self.server_socket:
            return
        try:
            client, _ = self.server_socket.accept()
            self._handle_request(client)
        except OSError:
            pass

    def _handle_request(self, client):
        """Handle an incoming HTTP request."""
        try:
            # Read initial chunk to get headers
            initial = client.recv(4096)
            if not initial:
                client.close()
                return

            header_end = initial.find(b'\r\n\r\n')
            if header_end == -1:
                client.close()
                return

            header_bytes = initial[:header_end]
            header_str = header_bytes.decode('utf-8')
            lines = header_str.split('\r\n')
            first_line = lines[0] if lines else ""
            parts = first_line.split(' ')
            method = parts[0] if parts else "GET"
            path = parts[1] if len(parts) > 1 else "/"

            # Parse Content-Length
            content_length = 0
            for line in lines[1:]:
                if line.lower().startswith('content-length:'):
                    content_length = int(line.split(':', 1)[1].strip())

            # Check session token
            token_path = "/" + self.session_token
            if not path.startswith(token_path):
                error_body = '''<!DOCTYPE html>
<html><head><meta name="viewport" content="width=device-width, initial-scale=1">
<style>body { font-family: sans-serif; text-align: center; padding: 50px 20px; }
h1 { color: #a94442; } .msg { background: #f2dede; padding: 20px; border-radius: 8px; color: #a94442; max-width: 400px; margin: 20px auto; }</style>
</head><body><h1>Access Denied</h1><div class="msg">Failed to access the config page. The session token in the URL is invalid.</div>
<p>Scan the QR code on the badge to get the correct URL.</p></body></html>'''
                response = "HTTP/1.1 403 Forbidden\r\nContent-Type: text/html\r\nConnection: close\r\n\r\n" + error_body
                client.send(response.encode('utf-8'))
                client.close()
                return

            sub_path = path[len(token_path):]

            # Read body
            body_bytes = initial[header_end + 4:]
            while len(body_bytes) < content_length:
                chunk = client.recv(4096)
                if not chunk:
                    break
                body_bytes += chunk

            # Route: image upload
            if method == "POST" and sub_path == "/image":
                self._handle_image_upload(client, body_bytes)
                return

            # Route: image delete
            if method == "POST" and sub_path == "/image/delete":
                self._handle_image_delete(client)
                return

            # Route: normal form or GET
            if method == "POST":
                response_body = self._handle_post(body_bytes.decode('utf-8'))
            else:
                response_body = self._get_settings_page()

            response = "HTTP/1.1 200 OK\r\nContent-Type: text/html\r\nConnection: close\r\n\r\n" + response_body
            client.send(response.encode('utf-8'))

        except Exception as e:
            tb = format_exception(e)
            print("Request error: " + str(e) + "\n" + tb)
            try:
                error_page = self._get_error_page(str(e), tb)
                response = "HTTP/1.1 500 Internal Server Error\r\nContent-Type: text/html\r\nConnection: close\r\n\r\n" + error_page
                client.send(response.encode('utf-8'))
            except:
                pass
        finally:
            client.close()

    def _handle_image_upload(self, client, body_bytes):
        """Handle image upload - body is raw JPEG bytes."""
        try:
            if len(body_bytes) > 35000:
                msg = "Image too large (max 30KB)"
            elif len(body_bytes) < 100:
                msg = "No image data received"
            else:
                with open(self.image_path, 'wb') as f:
                    f.write(body_bytes)
                # Add image to display fields if not already there
                display_fields = settings.get(KEY_DISPLAY_FIELDS) or [KEY_NAME]
                if IMAGE_FIELD not in display_fields:
                    display_fields.append(IMAGE_FIELD)
                    settings.set(KEY_DISPLAY_FIELDS, display_fields)
                    settings.save()
                self._load_settings()
                msg = "OK"
        except Exception as e:
            msg = "Error: " + str(e)
        client.send(("HTTP/1.1 200 OK\r\nContent-Type: text/plain\r\nConnection: close\r\n\r\n" + msg).encode('utf-8'))

    def _handle_image_delete(self, client):
        """Handle image delete request."""
        try:
            os.remove(self.image_path)
            # Remove image from display fields
            display_fields = settings.get(KEY_DISPLAY_FIELDS) or [KEY_NAME]
            if IMAGE_FIELD in display_fields:
                display_fields.remove(IMAGE_FIELD)
                settings.set(KEY_DISPLAY_FIELDS, display_fields)
                settings.save()
            self._load_settings()
            msg = "OK"
        except OSError:
            msg = "No image to delete"
        client.send(("HTTP/1.1 200 OK\r\nContent-Type: text/plain\r\nConnection: close\r\n\r\n" + msg).encode('utf-8'))

    def _handle_post(self, body):
        """Handle POST form submission."""
        try:
            data = parse_form(body)
            display_fields = settings.get(KEY_DISPLAY_FIELDS) or [KEY_NAME]
            message = "Settings saved!"

            # Handle delete/hide
            if "delete" in data:
                field_to_delete = data["delete"]
                if field_to_delete in display_fields and field_to_delete != KEY_NAME:
                    display_fields.remove(field_to_delete)
                    settings.set(KEY_DISPLAY_FIELDS, display_fields)
                    # EMF logo is just hidden, not deleted - no settings to clear
                    if field_to_delete == EMF_LOGO_FIELD:
                        message = "Hidden: EMFCamp logo"
                    else:
                        # Clear settings for regular fields
                        settings.set(field_to_delete, "")
                        settings.set(verb_key(field_to_delete), "")
                        for suffix in ["_hbg", "_hfg", "_vbg", "_vfg"]:
                            settings.set(field_to_delete + suffix, "")
                        message = "Removed field: " + display_name(field_to_delete)

            # Handle add field
            elif data.get("action") == "add_field" and data.get("new_field"):
                raw_name = data["new_field"].strip().lower().replace(" ", "_")
                fkey = field_key(raw_name)
                if fkey and fkey not in display_fields:
                    display_fields.append(fkey)
                    settings.set(KEY_DISPLAY_FIELDS, display_fields)
                    message = "Added field: " + raw_name

            # Handle show EMF logo
            elif data.get("action") == "show_emf_logo":
                if EMF_LOGO_FIELD not in display_fields:
                    display_fields.insert(0, EMF_LOGO_FIELD)
                    settings.set(KEY_DISPLAY_FIELDS, display_fields)
                    message = "EMFCamp logo shown"

            # Handle move up
            elif "move_up" in data:
                try:
                    idx = int(data["move_up"])
                    if idx > 0 and idx < len(display_fields):
                        display_fields[idx], display_fields[idx-1] = display_fields[idx-1], display_fields[idx]
                        settings.set(KEY_DISPLAY_FIELDS, display_fields)
                        message = "Field moved up"
                except (ValueError, IndexError):
                    pass

            # Handle move down
            elif "move_down" in data:
                try:
                    idx = int(data["move_down"])
                    if idx >= 0 and idx < len(display_fields) - 1:
                        display_fields[idx], display_fields[idx+1] = display_fields[idx+1], display_fields[idx]
                        settings.set(KEY_DISPLAY_FIELDS, display_fields)
                        message = "Field moved down"
                except (ValueError, IndexError):
                    pass

            # Handle save all
            elif data.get("action") == "save":
                for field in display_fields:
                    if field == IMAGE_FIELD or field == EMF_LOGO_FIELD:
                        continue
                    l1_key = "line1_" + field
                    l2_key = "line2_" + field
                    verb_k = "verb_" + field

                    # Save value as list of lines
                    if l1_key in data:
                        line1 = data[l1_key].strip()
                        line2 = data.get(l2_key, "").strip()
                        if line1 and line2:
                            settings.set(field, [line1, line2])
                        elif line1:
                            settings.set(field, [line1])
                        else:
                            settings.set(field, "")

                    if verb_k in data:
                        verb = data[verb_k]
                        if verb == "are":
                            settings.set(verb_key(field), verb)
                        else:
                            settings.set(verb_key(field), "")

                    # Save colour settings
                    for suffix in ["hbg", "hfg", "vbg", "vfg"]:
                        form_key = suffix + "_" + field
                        if form_key in data and data[form_key] in COLOUR_NAMES:
                            settings.set(field + "_" + suffix, data[form_key])

                # Save ICE settings
                settings.set(KEY_ICE_PHONE, data.get("ice_phone", ""))
                settings.set(KEY_ICE_NAME, data.get("ice_name", ""))
                settings.set(KEY_ICE_NOTES, data.get("ice_notes", ""))

                message = "All settings saved!"

            try:
                settings.save()
            except Exception as e:
                print("Save error: " + str(e))

            self._load_settings()
            return self._get_success_page(message)

        except Exception as e:
            tb = format_exception(e)
            print("POST error: " + str(e) + "\n" + tb)
            return self._get_error_page(str(e), tb)

    def _get_settings_page(self):
        """Generate the settings HTML page."""
        display_fields = settings.get(KEY_DISPLAY_FIELDS) or [KEY_NAME]

        field_rows = ""
        for field in display_fields:
            if field == IMAGE_FIELD or field == EMF_LOGO_FIELD:
                continue
            raw_value = settings.get(field)
            # Extract line1/line2 from list or string
            if isinstance(raw_value, list):
                line1 = raw_value[0] if len(raw_value) > 0 else ""
                line2 = raw_value[1] if len(raw_value) > 1 else ""
            else:
                line1 = raw_value or ""
                line2 = ""
            verb = settings.get(verb_key(field)) or "is"
            is_sel = "selected" if verb == "is" else ""
            are_sel = "selected" if verb == "are" else ""
            disp_name = html_esc(display_name(field))
            esc_field = html_esc(field)
            esc_line1 = html_esc(line1)
            esc_line2 = html_esc(line2)

            hbg = settings.get(field + "_hbg") or "red"
            hfg = settings.get(field + "_hfg") or "white"
            vbg = settings.get(field + "_vbg") or "black"
            vfg = settings.get(field + "_vfg") or "white"

            field_rows += '''
            <tr>
                <td>
                    my <b>''' + disp_name + '''</b>
                    <select class="verb" name="verb_''' + esc_field + '''">
                        <option value="is" ''' + is_sel + '''>is</option>
                        <option value="are" ''' + are_sel + '''>are</option>
                    </select>
                    <span class="cbox" id="box_hbg_''' + esc_field + '''" style="background:''' + hbg + '''" onclick="openPicker(''' + "'" + '''hbg_''' + esc_field + "'" + ''')">B</span>
                    <span class="cbox" id="box_hfg_''' + esc_field + '''" style="background:''' + hfg + '''" onclick="openPicker(''' + "'" + '''hfg_''' + esc_field + "'" + ''')">F</span>
                    <input type="hidden" name="hbg_''' + esc_field + '''" id="hbg_''' + esc_field + '''" value="''' + hbg + '''">
                    <input type="hidden" name="hfg_''' + esc_field + '''" id="hfg_''' + esc_field + '''" value="''' + hfg + '''">
                </td>
            </tr>
            <tr>
                <td>
                    <input type="text" name="line1_''' + esc_field + '''" value="''' + esc_line1 + '''" placeholder="Line 1">
                    <span class="cbox" id="box_vbg_''' + esc_field + '''" style="background:''' + vbg + '''" onclick="openPicker(''' + "'" + '''vbg_''' + esc_field + "'" + ''')">B</span>
                    <span class="cbox" id="box_vfg_''' + esc_field + '''" style="background:''' + vfg + '''" onclick="openPicker(''' + "'" + '''vfg_''' + esc_field + "'" + ''')">F</span>
                    <input type="hidden" name="vbg_''' + esc_field + '''" id="vbg_''' + esc_field + '''" value="''' + vbg + '''">
                    <input type="hidden" name="vfg_''' + esc_field + '''" id="vfg_''' + esc_field + '''" value="''' + vfg + '''">
                </td>
            </tr>
            <tr>
                <td>
                    <input type="text" name="line2_''' + esc_field + '''" value="''' + esc_line2 + '''" placeholder="Line 2 (optional)">
                </td>
            </tr>'''

        ice_phone = html_esc(settings.get(KEY_ICE_PHONE) or "")
        ice_name = html_esc(settings.get(KEY_ICE_NAME) or "")
        ice_notes = html_esc(settings.get(KEY_ICE_NOTES) or "")

        # Reorder section
        reorder_html = ""
        if len(display_fields) > 0:
            for i, field in enumerate(display_fields):
                # Display name for special fields
                if field == IMAGE_FIELD:
                    disp = "(image)"
                elif field == EMF_LOGO_FIELD:
                    disp = "EMFCamp"
                else:
                    disp = html_esc(display_name(field))
                esc_field = html_esc(field)
                idx_str = str(i)
                up_dis = "disabled" if i == 0 else ""
                down_dis = "disabled" if i == len(display_fields) - 1 else ""
                # Determine button: name can't be removed, EMF logo can be hidden, others removed
                if field == KEY_NAME or field == IMAGE_FIELD:
                    del_btn = ""
                elif field == EMF_LOGO_FIELD:
                    del_btn = '<button type="submit" name="delete" value="' + esc_field + '" style="background:#f0ad4e;color:white;border:none;">Hide</button>'
                else:
                    del_btn = '<button type="submit" name="delete" value="' + esc_field + '" style="background:#d9534f;color:white;border:none;">Remove</button>'
                reorder_html += '''
                <div style="margin: 5px 0;">
                    <span style="display: inline-block; width: 120px;">''' + disp + '''</span>
                    <button type="submit" name="move_up" value="''' + idx_str + '''" ''' + up_dis + '''>Up</button>
                    <button type="submit" name="move_down" value="''' + idx_str + '''" ''' + down_dis + '''>Down</button>
                    ''' + del_btn + '''
                </div>'''
        else:
            reorder_html = "<p>No fields to reorder.</p>"

        # Show EMF logo option if hidden
        emf_hidden_html = ""
        if EMF_LOGO_FIELD not in display_fields:
            emf_hidden_html = '''
    <form method="POST" action="''' + "/" + self.session_token + '''">
        <div class="section">
            <p>EMFCamp logo is hidden. <button type="submit" name="action" value="show_emf_logo" class="add-btn">Show EMFCamp Logo</button></p>
        </div>
    </form>'''

        action_url = "/" + self.session_token

        return '''<!DOCTYPE html>
<html>
<head>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Badge Settings</title>
    <style>
        body { font-family: sans-serif; max-width: 800px; margin: 0 auto; padding: 15px; }
        h1 { color: #333; font-size: 24px; margin-bottom: 20px; }
        h2 { color: #333; font-size: 18px; margin: 15px 0 10px 0; }
        h3 { font-size: 16px; margin: 15px 0 10px 0; }
        table { width: 100%; border-collapse: collapse; margin: 10px 0; }
        th, td { padding: 12px 8px; text-align: left; border-bottom: 1px solid #ddd; }
        input[type="text"], select { width: 100%; padding: 12px; box-sizing: border-box; font-size: 16px; border: 1px solid #ccc; border-radius: 4px; }
        button { padding: 12px 20px; margin: 8px 4px; cursor: pointer; font-size: 16px; border-radius: 4px; }
        .save-btn { background: #4CAF50; color: white; border: none; width: 100%; margin-top: 15px; }
        .add-btn { background: #2196F3; color: white; border: none; }
        .section { background: #f9f9f9; padding: 15px; margin: 15px 0; border-radius: 8px; }
        select { background: white; }
        select.verb { width: auto; display: inline; padding: 4px 8px; }
        .cbox { display: inline-block; width: 24px; height: 24px; border: 2px solid #333; border-radius: 4px; cursor: pointer; text-align: center; line-height: 24px; font-size: 11px; font-weight: bold; vertical-align: middle; margin-left: 4px; color: white; text-shadow: 0 0 2px black, 0 0 2px black; }
        #colorModal { display: none; position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.5); z-index: 999; align-items: center; justify-content: center; }
        .cpicker { background: white; padding: 20px; border-radius: 8px; text-align: center; max-width: 300px; }
        .cbtn { display: inline-block; width: 36px; height: 36px; margin: 4px; border: 2px solid #333; border-radius: 4px; cursor: pointer; }
    </style>
</head>
<body>
    <h1>Badge Settings</h1>

    <form method="POST" action="''' + action_url + '''">
        <div class="section">
            <h2>Display Fields</h2>
            <table>
                <tr><th>Screen shows</th></tr>
                ''' + field_rows + '''
            </table>
        </div>

        <div class="section">
            <h2>ICE (Emergency Contact)</h2>
            <table>
                <tr><td>Phone:</td><td><input type="text" name="ice_phone" value="''' + ice_phone + '''"></td></tr>
                <tr><td>Name:</td><td><input type="text" name="ice_name" value="''' + ice_name + '''"></td></tr>
                <tr><td>Notes:</td><td><input type="text" name="ice_notes" value="''' + ice_notes + '''" placeholder="e.g. allergies, conditions, medication"></td></tr>
            </table>
        </div>

        <button type="submit" name="action" value="save" class="save-btn">Save All Settings</button>
    </form>

    <form method="POST" action="''' + action_url + '''">
        <div class="section">
            <h3>Add Field</h3>
            <input type="text" name="new_field" placeholder="e.g. email, pronouns, company">
            <button type="submit" name="action" value="add_field" class="add-btn">Add</button>
        </div>
    </form>

    ''' + emf_hidden_html + '''

    <div class="section">
        <h2>Badge Image</h2>
        <p style="font-size:14px;color:#666;">Upload a 240x240 image to show in the badge rotation (max 30KB JPEG).</p>
        <input type="file" id="imgFile" accept="image/*" style="margin:8px 0;">
        <canvas id="imgPreview" width="240" height="240" style="display:none;border:1px solid #ccc;border-radius:4px;margin:8px 0;max-width:100%;"></canvas>
        <div id="imgStatus" style="margin:8px 0;font-size:14px;"></div>
        <button type="button" id="imgUpload" style="display:none;" class="add-btn">Upload Image</button>
        <button type="button" id="imgDelete" onclick="deleteImage()" style="background:#d9534f;color:white;border:none;">Delete Image</button>
    </div>

    <div class="section">
        <h2>Reorder or Remove</h2>
        <form method="POST" action="''' + action_url + '''">
            ''' + reorder_html + '''
        </form>
    </div>

    <p style="text-align:center;margin-top:20px;"><a href="https://github.com/JonTheNiceGuy/tildagon-my-conference-badge">GitHub</a></p>

    <div id="colorModal" onclick="closeModal()">
        <div class="cpicker" onclick="event.stopPropagation()">
            <p><b>Pick a colour</b></p>
            <div id="colorBtns"></div>
            <p style="margin-top:10px;"><button type="button" onclick="closeModal()">Cancel</button></p>
        </div>
    </div>

    <script>
    var activeInput=null;
    var colors=["black","white","gray","silver","maroon","red","purple","fuchsia","green","lime","olive","yellow","navy","blue","teal","aqua"];
    var btns="";
    for(var i=0;i<colors.length;i++){
        btns+='<span class="cbtn" style="background:'+colors[i]+'" data-color="'+colors[i]+'"></span>';
    }
    document.getElementById("colorBtns").innerHTML=btns;
    document.getElementById("colorBtns").addEventListener("click",function(e){
        if(e.target.dataset.color){pickColor(e.target.dataset.color);}
    });
    function openPicker(id){activeInput=id;document.getElementById("colorModal").style.display="flex";}
    function closeModal(){document.getElementById("colorModal").style.display="none";}
    function pickColor(c){
        document.getElementById(activeInput).value=c;
        document.getElementById("box_"+activeInput).style.background=c;
        closeModal();
    }

    // Image upload
    var imgCanvas=document.getElementById("imgPreview");
    var imgCtx=imgCanvas.getContext("2d");
    var imgBlob=null;
    var imgUrl="''' + action_url + '''/image";

    document.getElementById("imgFile").addEventListener("change",function(e){
        var file=e.target.files[0];
        if(!file)return;
        var img=new Image();
        img.onload=function(){
            imgCanvas.style.display="block";
            // Center-crop to square
            var s=Math.min(img.width,img.height);
            var sx=(img.width-s)/2,sy=(img.height-s)/2;
            imgCtx.drawImage(img,sx,sy,s,s,0,0,240,240);
            // Try decreasing quality to fit under 30KB
            var tryQuality=function(q){
                imgCanvas.toBlob(function(blob){
                    if(blob.size>30000&&q>0.2){
                        tryQuality(q-0.1);
                    }else{
                        imgBlob=blob;
                        var kb=(blob.size/1024).toFixed(1);
                        var status=document.getElementById("imgStatus");
                        if(blob.size>30000){
                            status.innerHTML="<b style=color:red>"+kb+"KB - too large even at min quality.</b>";
                            document.getElementById("imgUpload").style.display="none";
                        }else{
                            status.innerHTML=kb+"KB (quality "+Math.round(q*100)+"%) - ready to upload";
                            document.getElementById("imgUpload").style.display="inline-block";
                        }
                    }
                },"image/jpeg",q);
            };
            tryQuality(0.8);
        };
        img.src=URL.createObjectURL(file);
    });

    document.getElementById("imgUpload").addEventListener("click",function(){
        if(!imgBlob)return;
        var status=document.getElementById("imgStatus");
        status.innerHTML="Uploading...";
        fetch(imgUrl,{method:"POST",body:imgBlob}).then(function(r){return r.text();}).then(function(t){
            if(t==="OK"){status.innerHTML="<b style=color:green>Uploaded!</b>";document.getElementById("imgUpload").style.display="none";}
            else{status.innerHTML="<b style=color:red>"+t+"</b>";}
        }).catch(function(e){status.innerHTML="<b style=color:red>Upload failed</b>";});
    });

    function deleteImage(){
        if(!confirm("Delete badge image?"))return;
        fetch(imgUrl+"/delete",{method:"POST"}).then(function(r){return r.text();}).then(function(t){
            document.getElementById("imgStatus").innerHTML=(t==="OK")?"<b>Image deleted</b>":"<b>"+t+"</b>";
        }).catch(function(){document.getElementById("imgStatus").innerHTML="<b style=color:red>Delete failed</b>";});
    }
    </script>
</body>
</html>'''

    def _get_success_page(self, message):
        url = "/" + self.session_token
        return '''<!DOCTYPE html>
<html><head><meta http-equiv="refresh" content="1;url=''' + url + '''">
<style>body { font-family: sans-serif; text-align: center; padding: 50px; }
.ok { background: #dff0d8; padding: 20px; border-radius: 5px; color: #3c763d; }</style>
</head><body><div class="ok">''' + html_esc(message) + '''</div><p>Redirecting...</p></body></html>'''

    def _get_error_page(self, error, tb=""):
        tb_html = ""
        if tb:
            tb_html = '<pre style="background:#333;color:#fff;padding:10px;overflow-x:auto;">' + html_esc(tb) + '</pre>'
        url = "/" + self.session_token
        return '''<!DOCTYPE html>
<html><head><style>body { font-family: sans-serif; padding: 20px; }
.err { background: #f2dede; padding: 20px; border-radius: 5px; color: #a94442; }</style>
</head><body><h1>Error</h1><div class="err">''' + html_esc(error) + '''</div>''' + tb_html + '''
<p><a href="''' + url + '''">Back</a></p></body></html>'''
