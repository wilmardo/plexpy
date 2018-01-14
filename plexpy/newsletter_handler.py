﻿#  This file is part of Tautulli.
#
#  Tautulli is free software: you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation, either version 3 of the License, or
#  (at your option) any later version.
#
#  Tautulli is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License
#  along with Tautulli.  If not, see <http://www.gnu.org/licenses/>.

import time

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

import plexpy
import database
import logger
import newsletters


NEWSLETTER_SCHED = BackgroundScheduler()


def schedule_newsletters(newsletter_id=None):
    newsletters_list = newsletters.get_newsletters(newsletter_id=newsletter_id)

    for newsletter in newsletters_list:
        newsletter_job_name = '{} ({})'.format(newsletter['agent_label'],
                                               newsletter['friendly_name'] or newsletter['id'])

        if newsletter['active']:
            schedule_newsletter_job('newsletter-{}'.format(newsletter['id']), name=newsletter_job_name,
                                    func=notify, args=[newsletter['id'], 'on_cron'], cron=newsletter['cron'])
        else:
            schedule_newsletter_job('newsletter-{}'.format(newsletter['id']), name=newsletter_job_name,
                                    remove_job=True)


def schedule_newsletter_job(newsletter_job_id, name='', func=None, remove_job=False, args=None, cron=None):
    if NEWSLETTER_SCHED.get_job(newsletter_job_id):
        if remove_job:
            NEWSLETTER_SCHED.remove_job(newsletter_job_id)
            logger.info(u"Tautulli NewsletterHandler :: Removed scheduled newsletter: %s" % name)
        else:
            NEWSLETTER_SCHED.reschedule_job(
                newsletter_job_id, args=args, trigger=CronTrigger().from_crontab(cron))
            logger.info(u"Tautulli NewsletterHandler :: Re-scheduled newsletter: %s" % name)
    elif not remove_job:
        NEWSLETTER_SCHED.add_job(
            func, args=args, id=newsletter_job_id, trigger=CronTrigger.from_crontab(cron))
        logger.info(u"Tautulli NewsletterHandler :: Scheduled newsletter: %s" % name)


def notify(newsletter_id=None, notify_action=None, **kwargs):
    logger.info(u"Tautulli NewsletterHandler :: Preparing newsletter for newsletter_id %s." % newsletter_id)

    newsletter_config = newsletters.get_newsletter_config(newsletter_id=newsletter_id)

    if not newsletter_config:
        return

    if notify_action in ('test', 'api'):
        subject_string = kwargs.pop('subject', 'Tautulli Newsletter')
    else:
        # Get the subject string
        subject_string = newsletter_config['email_config']['subject']

    newsletter_agent = newsletters.get_agent_class(agent_id=newsletter_config['agent_id'],
                                                   config=newsletter_config['config'],
                                                   email_config=newsletter_config['email_config'])
    subject = newsletter_agent.format_subject(subject_string)

    # Set the newsletter state in the db
    newsletter_log_id = set_notify_state(newsletter=newsletter_config,
                                         notify_action=notify_action,
                                         subject=subject)

    # Send the notification
    success = newsletters.send_newsletter(newsletter_id=newsletter_config['id'],
                                          subject=subject,
                                          notify_action=notify_action,
                                          newsletter_log_id=newsletter_log_id,
                                          **kwargs)

    if success:
        set_notify_success(newsletter_log_id)
        return True


def set_notify_state(newsletter, notify_action, subject):

    if newsletter and notify_action:
        monitor_db = database.MonitorDatabase()

        keys = {'timestamp': int(time.time()),
                'newsletter_id': newsletter['id'],
                'agent_id': newsletter['agent_id'],
                'notify_action': notify_action}

        values = {'agent_name': newsletter['agent_name'],
                  'subject_text': subject}

        monitor_db.upsert(table_name='newsletter_log', key_dict=keys, value_dict=values)
        return monitor_db.last_insert_id()
    else:
        logger.error(u"Tautulli NewsletterHandler :: Unable to set notify state.")


def set_notify_success(newsletter_log_id):
    keys = {'id': newsletter_log_id}
    values = {'success': 1}

    monitor_db = database.MonitorDatabase()
    monitor_db.upsert(table_name='newsletter_log', key_dict=keys, value_dict=values)
