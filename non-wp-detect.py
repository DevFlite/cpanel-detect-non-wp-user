#!/usr/bin/env python3
import os
import glob
import csv
import pwd

SYSTEM_USERS = {"system", "nobody", "cpanel", "root"}

def get_cpanel_users():
    """Retrieves a list of valid cPanel users, excluding system accounts."""
    cpanel_users = []
    users_dir = "/var/cpanel/users"
    if os.path.exists(users_dir):
        for entry in os.listdir(users_dir):
            if entry.startswith(".") or entry in SYSTEM_USERS:
                continue
            full_path = os.path.join(users_dir, entry)
            if os.path.isfile(full_path):
                cpanel_users.append(entry)
    return sorted(cpanel_users)

def get_user_primary_domain(username):
    """Retrieves the primary domain for a cPanel user using multiple fallback sources."""
    # 1. Check /etc/trueuserdomains (standard cPanel mapping: 'domain.com: username')
    trueuserdomains_path = "/etc/trueuserdomains"
    if os.path.exists(trueuserdomains_path):
        try:
            with open(trueuserdomains_path, "r", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    parts = line.strip().split(":")
                    if len(parts) >= 2 and parts[1].strip() == username:
                        return parts[0].strip()
        except Exception:
            pass

    # 2. Check /var/cpanel/userdata/<username>/main
    main_file = f"/var/cpanel/userdata/{username}/main"
    if os.path.exists(main_file):
        try:
            with open(main_file, "r", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    if line.strip().startswith("main_domain:"):
                        domain = line.split(":", 1)[1].strip().strip("'\"")
                        if domain:
                            return domain
        except Exception:
            pass

    # 3. Check /var/cpanel/users/<username>
    user_file = f"/var/cpanel/users/{username}"
    if os.path.exists(user_file):
        try:
            with open(user_file, "r", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    line_clean = line.strip()
                    for prefix in ("DNS=", "domain=", "DOMAIN="):
                        if line_clean.startswith(prefix):
                            domain = line_clean.split("=", 1)[1].strip().strip("'\"")
                            if domain:
                                return domain
        except Exception:
            pass

    return "Unknown"

def get_user_docroots(username):
    """Collects all document roots for a user using multiple discovery methods."""
    docroots = set()

    # 1. Check /etc/userdatadomains (consolidated format: domain: user==owner==type==parent==docroot==...)
    userdatadomains_path = "/etc/userdatadomains"
    if os.path.exists(userdatadomains_path):
        try:
            with open(userdatadomains_path, "r", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    line_clean = line.strip()
                    if f": {username}==" in line_clean:
                        parts = line_clean.split("==")
                        if len(parts) >= 5:
                            dr = parts[4].strip().strip("'\"")
                            if dr:
                                docroots.add(dr)
        except Exception:
            pass

    # 2. Parse individual /var/cpanel/userdata/<username>/* files
    userdata_dir = f"/var/cpanel/userdata/{username}"
    if os.path.exists(userdata_dir):
        for conf_file in glob.glob(os.path.join(userdata_dir, "*")):
            base_conf = os.path.basename(conf_file)
            if conf_file.endswith(".cache") or base_conf == "main" or os.path.isdir(conf_file):
                continue
            try:
                with open(conf_file, "r", encoding="utf-8", errors="ignore") as f:
                    for line in f:
                        if line.strip().startswith("documentroot:"):
                            parts = line.split(":", 1)
                            if len(parts) > 1:
                                dr = parts[1].strip().strip("'\"")
                                if dr:
                                    docroots.add(dr)
            except Exception:
                continue

    # 3. Dynamic fallback using actual home directory (supports /home, /home2, etc.)
    try:
        user_home = pwd.getpwnam(username).pw_dir
    except KeyError:
        user_home = f"/home/{username}"

    fallback_public_html = os.path.join(user_home, "public_html")
    if os.path.isdir(fallback_public_html):
        docroots.add(fallback_public_html)

    return list(docroots)

def has_wordpress(docroots):
    """Checks if any of the given document roots contain a WordPress installation."""
    for dr in docroots:
        if not os.path.isdir(dr):
            continue

        # Check root level of document root
        wp_config = os.path.join(dr, "wp-config.php")
        wp_login = os.path.join(dr, "wp-login.php")
        wp_content = os.path.join(dr, "wp-content")

        if os.path.isfile(wp_config) or os.path.isfile(wp_login) or os.path.isdir(wp_content):
            return True

        # Check 1-level subdirectories (e.g. /public_html/wordpress, /public_html/wp, /public_html/blog)
        try:
            for item in os.listdir(dr):
                sub_dir = os.path.join(dr, item)
                if os.path.isdir(sub_dir):
                    if (os.path.isfile(os.path.join(sub_dir, "wp-config.php")) or
                        os.path.isfile(os.path.join(sub_dir, "wp-login.php")) or
                        os.path.isdir(os.path.join(sub_dir, "wp-content"))):
                        return True
        except (PermissionError, OSError):
            continue

    return False

def main():
    if os.geteuid() != 0:
        print("[-] Error: This script must be run as root.")
        return

    csv_filename = "cpanel_accounts_without_wordpress.csv"
    users = get_cpanel_users()

    print("=" * 65)
    print("Scanning cPanel accounts for missing WordPress installations...")
    print("=" * 65)
    print(f"{'USERNAME':<15} | {'PRIMARY DOMAIN':<30} | {'STATUS'}")
    print("-" * 65)

    no_wp_count = 0
    results = []

    for user in users:
        primary_domain = get_user_primary_domain(user)
        docroots = get_user_docroots(user)

        if not has_wordpress(docroots):
            print(f"{user:<15} | {primary_domain:<30} | No WordPress Found")
            results.append({
                "Username": user,
                "Primary Domain": primary_domain,
                "Status": "No WordPress Found"
            })
            no_wp_count += 1

    # Write results to CSV file
    try:
        with open(csv_filename, mode="w", newline="", encoding="utf-8") as csv_file:
            fieldnames = ["Username", "Primary Domain", "Status"]
            writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
            writer.writeheader()
            for row in results:
                writer.writerow(row)
        print("=" * 65)
        print(f"Scan complete. Found {no_wp_count} accounts without WordPress.")
        print(f"[+] Results successfully exported to: {os.path.abspath(csv_filename)}")
    except Exception as e:
        print(f"[-] Error writing CSV file: {e}")

if __name__ == "__main__":
    main()