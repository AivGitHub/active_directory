from django.db import models
from django.utils.translation import gettext_lazy as _
import ldap3


class Settings(models.Model):
    username = models.CharField(
        _('AD Username'), max_length=256, null=True, blank=True,
        help_text=_('Username should contain \'@\' or \'\\\' or be empty if you want to use settings only for login'))
    password = models.CharField(_('Password of AD user'), max_length=128, null=True, blank=True)
    domain = models.CharField(_('Domain controller'), max_length=256, null=False, blank=False, unique=True)
    ssl = models.BooleanField(_('SSL'), default=False, null=False, blank=False)
    port = models.PositiveIntegerField(_('Active directory port'), default=389, blank=False)

    class Meta:
        verbose_name = (_('Active directory setting'))
        verbose_name_plural = (_('Active directory settings'))

    def __str__(self):
        return str(self.domain)

    @staticmethod
    def locate_domain_controllers():
        return []

    @staticmethod
    def get_user_principal_name(username):
        """
        :username: username
        :return: user normal name (userPrincipalName) or None
        """

        if username is None:
            return None

        username = str(username)

        if '@' in username:
            return username
        elif '\\' in username:
            # For mammoths
            # domain\username is the same as username@domain
            return '@'.join(reversed(username.split('\\')))
        else:
            return None

    def save(self, *args, **kwargs):

        if self.username:
            self.username = self.username.strip()
        if self.domain:
            self.domain = self.domain.strip()

        if not self.username:
            self.username = None
            self.password = None

        super().save(*args, **kwargs)

    def get_search_base(self):
        """
        :username: username
        :return: search base or distinguished name (dn)
        """
        username = self.get_user_principal_name(self.username)
        return ''.join([f'dc={u},' for u in username.split('@')[1].split('.')]).strip(',')

    def get_connection(self, login_username=None, login_password=None):
        """
        :login_username: username to establish ldap connection. Use settings login if None
        :login_password: password to establish ldap connection. Use settings password if None
        :return: search base (distinguished name) and ldap connection OR None, None
        """
        if not login_username:
            login_username = self.username
            login_password = self.password

        server = ldap3.Server(self.domain, port=self.port, use_ssl=self.ssl,
                              get_info=ldap3.ALL)
        username = self.get_user_principal_name(login_username)

        try:
            return ldap3.Connection(server, username, login_password, auto_bind=True)
        except (ldap3.core.exceptions.LDAPSocketOpenError, ldap3.core.exceptions.LDAPBindError) as e:
            raise e

    def get_users_info_ad(self, login_username=None, login_password=None, users=None, attributes='*'):

        if not users:
            search_filter = '(objectClass=person)'
        else:
            if not isinstance(users, (list, tuple)):
                raise ldap3.core.exceptions.LDAPException('Users must be list/tuple of users or None')

            sam_account_names = ''.join([f'(sAMAccountName={str(user).strip()})' for user in users])
            search_filter = f'(&(objectClass=person)(|{sam_account_names}))'

        results = []
        search_base = self.get_search_base()
        connection = self.get_connection(login_username=login_username, login_password=login_password)

        if connection is None:
            raise ldap3.core.exceptions.LDAPException('No active AD connections found')

        for entry in connection.extend.standard.paged_search(
            search_base=search_base,
            search_filter=search_filter,
            search_scope=ldap3.SUBTREE,
            attributes=attributes,
            paged_size=500,
            generator=True
        ):
            # Remove searchResRef results
            if entry.get('type') != 'searchResRef':
                results.append(entry)

        if connection is not None:
            connection.unbind()

        # It's normal not to yield but to return here
        # TODO think: or yield each result?
        return results


class ADUser(models.Model):
    username = models.CharField(_('AD Username'), max_length=256, null=False, blank=False)
    mail = models.CharField(_('Mail address'), max_length=256, null=True, blank=True)
    organizational_unit = models.CharField(_('Organizational unit'), max_length=64, null=True, blank=True)
    user_principal_name = models.CharField(_('User principal name'), max_length=1024, null=True, blank=True)
    sam_account_name = models.CharField(_('Sam account name'), max_length=32, null=True, blank=True)

    def __str__(self):
        return self.user_principal_name


# https://docs.microsoft.com/ru-ru/troubleshoot/windows-server/identity/useraccountcontrol-manipulate-account-properties
class UserAccountControlValues(object):
    SCRIPT = 1
    ACCOUNTDISABLE = 2
    HOMEDIR_REQUIRED = 8
    LOCKOUT = 16
    PASSWD_NOTREQD = 32
    PASSWD_CANT_CHANGE = 64
    ENCRYPTED_TEXT_PWD_ALLOWED = 128
    TEMP_DUPLICATE_ACCOUNT = 256
    NORMAL_ACCOUNT = 512
    INTERDOMAIN_TRUST_ACCOUNT = 2048
    WORKSTATION_TRUST_ACCOUNT = 4096
    SERVER_TRUST_ACCOUNT = 8192
    DONT_EXPIRE_PASSWORD = 65536
    MNS_LOGON_ACCOUNT = 131072
    SMARTCARD_REQUIRED = 262144
    TRUSTED_FOR_DELEGATION = 524288
    NOT_DELEGATED = 1048576
    USE_DES_KEY_ONLY = 2097152
    DONT_REQ_PREAUTH = 4194304
    PASSWORD_EXPIRED = 8388608
    TRUSTED_TO_AUTH_FOR_DELEGATION = 16777216
    PARTIAL_SECRETS_ACCOUNT = 67108864
