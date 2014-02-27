from peewee import *

from app import Account, PageView


DEFAULT_ACCOUNT_ID = 1

class Report(object):
    def __init__(self, account_id=DEFAULT_ACCOUNT_ID):
        self.account = Account.get(Account.id == account_id)
        self.date_range = None

    def get_query(self):
        query = PageView.select().where(PageView.account == self.account)
        if self.date_range:
            query = query.where(PageView.timestamp.between(*self.date_range))
        return query

    def top_pages_by_time_period(self, interval='day'):
        """
        Get a breakdown of top pages per interval, i.e.

        day         url     count
        2014-01-01  /blog/  11
        2014-01-02  /blog/  14
        2014-01-03  /blog/  9
        """
        date_trunc = fn.date_trunc(interval, PageView.timestamp)
        return (self.get_query()
                .select(
                    PageView.url,
                    date_trunc.alias(interval),
                    fn.Count(PageView.id).alias('count'))
                .group_by(PageView.url, date_trunc)
                .order_by(
                    SQL(interval),
                    SQL('count').desc(),
                    PageView.url))

    def cookies(self):
        """
        Retrieve the cookies header from all the users who visited.
        """
        return (self.get_query()
                .select(PageView.ip, PageView.headers['Cookie'])
                .where(~(PageView.headers['Cookie'] >> None))
                .tuples())

    def user_agents(self):
        """
        Retrieve user-agents, sorted by most common to least common.
        """
        return (self.get_query()
                .select(
                    PageView.headers['User-Agent'],
                    fn.Count(PageView.id))
                .group_by(PageView.headers['User-Agent'])
                .order_by(fn.Count(PageView.id).desc())
                .tuples())

    def languages(self):
        """
        Retrieve languages, sorted by most common to least common. The
        Accept-Languages header sometimes looks weird, i.e.
        "en-US,en;q=0.8,is;q=0.6,da;q=0.4" We will split on the first semi-
        colon.
        """
        language = PageView.headers['Accept-Language']
        first_language = fn.SubStr(
            language,  # String to slice.
            1,  # Left index.
            fn.StrPos(language, ';'))
        return (self.get_query()
                .select(first_language, fn.Count(PageView.id))
                .group_by(first_language)
                .order_by(fn.Count(PageView.id).desc())
                .tuples())

    def trail(self):
        """
        Get all visitors by IP and then list the pages they visited in order.
        """
        inner = (self.get_query()
                 .select(PageView.ip, PageView.url)
                 .order_by(PageView.timestamp))
        return (PageView
                .select(
                    PageView.ip,
                    fn.array_agg(PageView.url).coerce(False).alias('urls'))
                .from_(inner.alias('t1'))
                .group_by(PageView.ip))

    def _referrer_clause(self, domain_only=True):
        if domain_only:
            return fn.SubString(Clause(
                PageView.referrer, SQL('FROM'), '.*://([^/]*)'))
        return PageView.referrer

    def top_referrers(self, domain_only=True):
        """
        What domains send us the most traffic?
        """
        referrer = self._referrer_clause(domain_only)
        return (self.get_query()
                .select(referrer, fn.Count(PageView.id))
                .group_by(referrer)
                .order_by(fn.Count(PageView.id).desc())
                .tuples())

    def referrers_for_url(self, domain_only=True):
        referrer = self._referrer_clause(domain_only)
        return (self.get_query()
                .select(PageView.url, referrer, fn.Count(PageView.id))
                .group_by(PageView.url, referrer)
                .order_by(PageView.url, fn.Count(PageView.id).desc())
                .tuples())

    def referrers_to_url(self, domain_only=True):
        referrer = self._referrer_clause(domain_only)
        return (self.get_query()
                .select(referrer, PageView.url, fn.Count(PageView.id))
                .group_by(referrer, PageView.url)
                .order_by(referrer, fn.Count(PageView.id).desc())
                .tuples())
