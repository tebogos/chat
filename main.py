# -*- coding: utf-8 -*-

from random import choice
from django.utils import simplejson
from google.appengine.api import channel, memcache, users
from google.appengine.ext.webapp.util import run_wsgi_app
from google.appengine.ext import webapp


ANONYMOUS_IDS = set(range(1, 1000)) # you can increase it for accepting more anonymous users

def broadcast(message, tokens=None):
	if not tokens:
		tokens = memcache.get('tokens')
	if tokens:
		tokens.pop('_used_ids', None) # make sure you won't use the tokens after broadcast(), otherwise you need do a copy
		ids = set(tokens.values()) # remove duplicate ids
		# be noticed that a logged in user may connect to 1 channel by using several browsers at the same time
		# it works strange both in the cloud and local server:
		#   1. if removed the duplicate ids, only the last connected browser can receive the message
		#   2. if not removed them, all the browsers will receive duplicate messages
		# I don't know if it's a bug of the SDK 1.4.0
		for id in ids: # it may take a while if there are many users in the room, I think you can use task queue to handle this problem
			if isinstance(id, int):
				id = 'anonymous(%s)' % id
			channel.send_message(id, message)

class GetTokenHandler(webapp.RequestHandler):
	def get(self):
		tokens = memcache.get('tokens') or {}
		user = users.get_current_user()
		if user:
			channel_id = id = user.email() # you can use hash algorithm for ensuring the channel id is less then 64 bytes
		else:
			used_ids = tokens.get('_used_ids') or set()
			available_ids = ANONYMOUS_IDS - used_ids
			if available_ids:
				available_ids = list(available_ids)
			else:
				self.response.out.write('')
				return
			id = choice(available_ids)
			used_ids.add(id)
			tokens['_used_ids'] = used_ids
			channel_id = 'anonymous(%s)' % id
		token = channel.create_channel(channel_id)
		tokens[token] = id
		memcache.set('tokens', tokens) # you can use datastore instead of memcache
		self.response.out.write(token)

class ReleaseTokenHandler(webapp.RequestHandler):
	def post(self):
		token = self.request.get('token')
		if not token:
			return
		tokens = memcache.get('tokens')
		if tokens:
			id = tokens.get(token, '')
			if id:
				if isinstance(id, int):
					used_ids = tokens.get('_used_ids')
					if used_ids:
						used_ids.discard(id)
						tokens['_used_ids'] = used_ids
					user_name = 'anonymous(%s)' % id
				else:
					user_name = id.split('@')[0]
				del tokens[token]
				memcache.set('tokens', tokens)
				message = user_name + ' has left the chat room.'
				message = simplejson.dumps(message)
				broadcast(message, tokens)


class OpenHandler(webapp.RequestHandler):
	def post(self):
		token = self.request.get('token')
		if not token:
			return
		tokens = memcache.get('tokens')
		if tokens:
			id = tokens.get(token, '')
			if id:
				if isinstance(id, int):
					user_name = 'anonymous(%s)' % id
				else:
					user_name = id.split('@')[0]
				message = user_name + u' has joined the chat room.'
				message = simplejson.dumps(message)
				broadcast(message, tokens)


class ReceiveHandler(webapp.RequestHandler):
	def post(self):
		token = self.request.get('token')
		if not token:
			return
		message = self.request.get('content')
		if not message:
			return
		tokens = memcache.get('tokens')
		if tokens:
			id = tokens.get(token, '')
			if id:
				if isinstance(id, int):
					user_name = 'anonymous(%s)' % id
				else:
					user_name = id.split('@')[0]
				message = '%s: %s' % (user_name, message)
				message = simplejson.dumps(message)
				if len(message) > channel.MAXIMUM_MESSAGE_LENGTH:
					return
				broadcast(message)

class LoginOrOut(webapp.RequestHandler):
	def get(self):
		if users.get_current_user():
			self.redirect(users.create_logout_url('/'))
		else:
			self.redirect(users.create_login_url('/'))

application = webapp.WSGIApplication([('/post_msg', ReceiveHandler),
									 ('/get_token', GetTokenHandler),
									 ('/del_token', ReleaseTokenHandler),
									 ('/open', OpenHandler),
									 ('/login', LoginOrOut)])

def main():
	run_wsgi_app(application)


if __name__ == '__main__':
	main()
