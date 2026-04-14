# My Conference Badge

This is my primary use for the Tildagon; telling everyone who I am and how to get in touch with me.

This app draws on the [hello-name-badge](https://github.com/jake-walker/tildagon-name-badge) app by Jake Walker, and expands it significantly.

If you've already installed Jake's badge app, then it'll immediately know about your name, but to add more details press the "D" button (the bottom button) and confirm you want to start the web server by pressing "E" (bottom left) within 5 seconds. This will open a QR code which will let you customize the settings to your heart's content.

Add more details, like your handle on Matrix, Mastodon or your blog address. Set your pronouns and the company you work for.

You'll also notice "ICE" (or In Case of Emergency). You can set a "Someone" who should be contacted in an emergency, their name and number. You can also provide any medical details for you.

To get to this, press "B" (top right) and confirm with "E" (bottom left) within 5 seconds. This will show your ICE contact details. Press "B" (top right) again to see your medical details.

## Customising the Conference Logo

This app looks for event logos in the `event_images/` directory and lists them alphabetically in the web settings interface, where you can select which one to display. The display name is derived from the filename (e.g. `oggcamp-2026.jpg` becomes `oggcamp 2026`).

To add your own event logo:

1. Prepare your image as a **240x240 pixel JPEG**, under **30KB** in size.
2. You can use a command like this to convert your source image:
   ```bash
   python3 -c "
   from PIL import Image
   img = Image.open('your_logo.png')
   if img.mode in ('RGBA', 'LA', 'P'):
       bg = Image.new('RGB', img.size, (0, 0, 0))
       img_rgba = img.convert('RGBA')
       bg.paste(img_rgba, mask=img_rgba.split()[3])
       img = bg
   size = min(img.size)
   left, top = (img.width - size) // 2, (img.height - size) // 2
   img = img.crop((left, top, left + size, top + size))
   img = img.resize((240, 240), Image.Resampling.LANCZOS)
   img.save('event_images/myevent-2026.jpg', 'JPEG', quality=85)
   "
   ```
3. Place the JPEG in the `event_images/` directory and redeploy. It will appear automatically in the Event Logo selector in the web settings.

The logo can be hidden or reordered via the web settings interface.

## Pull Requests, Feature Requests and Forks

Please don't hesitate to raise a Pull and Feature Requests against this repo. I mainly forked this from the original Jake Walker version because of how many changes I made to their repo, and I didn't feel it would be fair to ask them to support this giant amount of changes. I am happy for you to contribute to this, or fork it for yourself. It is released under the "[Unlicense](LICENSE)" and thus you are free to do as you will with it, caveat the following two statements.

## Security issues

I am aware of the fact that using an HTTP server on public wifi isn't a *great* idea. I've tried to reduce the risk slightly by only running the HTTP server while the QR code is on, and by making the target URL have a little bit of randomness to the URL. That said, it's still passing plain-text content over the wire, so if anyone wants to improve this, I'd be grateful for some guidance!

If you find any other security issues with this, please do [contact me directly](mailto:my-conf-badge-sec-issue@jon.sprig.gs) and I'll do what I can to help.

## LLM/"AI" notification

This project was enhanced with the support of the Claude Code application from Anthropic. If you feel like your code has been misused in my work, please [contact me](mailto:my-conf-badge-llm-issue@jon.sprig.gs) and we can talk about remediating the issue.

Complaints about the use of LLMs or "AI" will be ignored.