#!/usr/bin/env python3
import os
import glob
import csv
import pwd

def get_cpanel_users():
    """Retrieves a list of valid cPanel users."""
    cpanel_users = []
    users_dir = "/var/cpanel/users"
    if os.path.exists(users_dir):
        cpanel_users = os.listdir(users_dir)
    return cpanel_users

def get_user_primary_domain(username):
    """Retrieves the primary domain for a cPanel user."""
    user_file = f"/var/cpanel/users/{username}"
    if os.path.exists(user_file):
        try:
            with open(user_file, "r", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    if line.startswith("domain="):
                        return line.split("=", 1)[1].strip()
        except Exception:
            pass
    return "Unknown"

def get_user_docroots(username):
    """Parses cPanel userdata files to find all document roots for a user."""
    docroots = []
    userdata_dir = f"/var/cpanel/userdata/{username}"
    
    if os.path.exists(userdata_dir):
        for conf_file in glob.glob(os.path.join(userdata_dir, "*")):
            if conf_file.endswith(".cache") or os.path.isdir(conf_file):
                continue
            try:
                with open(conf_file, "r", encoding="utf-8", errors="ignore") as f:
                    for line in f:
                        if line.strip().startswith("documentroot:"):
                            parts = line.split(":", 1)
                            if len(parts) > 1:
                                docroot = parts[1].strip()
                                if docroot and docroot not in docroots:
                                    docroots.append(docroot)
            except Exception:
                continue
                
    # Fallback if no userdata found: check standard public_html
    if not docroots:
        fallback = f"/home/{username}/public_html"
        if os.path.exists(fallback):
            docroots.append(fallback)
            
    return docroots

def has_wordpress(docroots):
    """Checks if any of the given document roots contain a WordPress installation."""
    for dr in docroots:
        if not os.path.exists(dr):
            continue
        wp_config = os.path.join(dr, "wp-config.php")
        wp_login = os.path.join(dr, "wp-login.php")
        wp_content = os.path.join(dr, "wp-content")
        
        if os.path.isfile(wp_config) or os.path.isfile(wp_login) or os.path.isdir(wp_content):
            return True
    return False

def main():
    if os.geteuid() != 0:
        print("[-] Error: This script must be run as root.")
        return

    csv_filename = "cpanel_accounts_without_wordpress.csv"
    users = get_cpanel_users()
    
    print("=" * 65)
    print(f"{'USERNAME':<15} | {'PRIMARY DOMAIN':<25} | {'STATUS'}")
    print("-" * 65)

    no_wp_count = 0
    results = []

    for user in sorted(users):
        primary_domain = get_user_primary_domain(user)
        docroots = get_user_docroots(user)
        
        if not has_wordpress(docroots):
            print(f"{user:<15} | {primary_domain:<25} | No WordPress Found")
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