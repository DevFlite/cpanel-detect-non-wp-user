#!/bin/bash

# Ensure script is run as root
if [ "$EUID" -ne 0 ]; then
    echo "[-] Error: Please run this script as root."
    exit 1
fi

CSV_FILE="cpanel_accounts_without_wordpress.csv"
TEMP_FILE=$(mktemp)

# Initialize CSV header
echo "Username,Primary Domain,Status" > "$CSV_FILE"

echo "================================================================="
echo "Scanning cPanel accounts for missing WordPress installations..."
echo "================================================================="
printf "%-15s | %-25s | %s\n" "USERNAME" "PRIMARY DOMAIN" "STATUS"
echo "-----------------------------------------------------------------"

no_wp_count=0

# Loop through all valid cPanel users based on /var/cpanel/users directory
for user_file in /var/cpanel/users/*; do
    [ -f "$user_file" ] || continue
    user=$(basename "$user_file")

    # Extract primary domain
    domain=$(grep '^domain=' "$user_file" | cut -d= -f2)
    [ -z "$domain" ] && domain="Unknown"

    has_wp=0
    userdata_dir="/var/cpanel/userdata/$user"

    # Check all domain document roots (Primary + Addons/Subdomains)
    if [ -d "$userdata_dir" ]; then
        for conf in "$userdata_dir"/*; do
            if [ -f "$conf" ] && [[ "$conf" != *.cache ]]; then
                docroot=$(grep -E '^\s*documentroot:' "$conf" | awk '{print $2}')
                
                if [ -n "$docroot" ] && [ -d "$docroot" ]; then
                    # Check for core WordPress indicator files/directories
                    if [ -f "$docroot/wp-config.php" ] || [ -f "$docroot/wp-login.php" ] || [ -d "$docroot/wp-content" ]; then
                        has_wp=1
                        break
                    fi
                fi
            fi
        done
    fi

    # Fallback to standard public_html if userdata check found nothing
    if [ "$has_wp" -eq 0 ]; then
        fallback_dir="/home/$user/public_html"
        if [ -d "$fallback_dir" ]; then
            if [ -f "$fallback_dir/wp-config.php" ] || [ -f "$fallback_dir/wp-login.php" ] || [ -d "$fallback_dir/wp-content" ]; then
                has_wp=1
            fi
        fi
    fi

    # If WordPress is missing across all document roots
    if [ "$has_wp" -eq 0 ]; then
        printf "%-15s | %-25s | %s\n" "$user" "$domain" "No WordPress Found"
        echo "$user,$domain,No WordPress Found" >> "$CSV_FILE"
        ((no_wp_count++))
    fi

done

echo "================================================================="
echo "Scan complete. Found $no_wp_count accounts without WordPress."
echo "[+] Results successfully exported to: $(pwd)/$CSV_FILE"