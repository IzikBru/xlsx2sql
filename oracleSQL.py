# this page is specific for OracleDB, each new RDBMS need to implement the queries accordingly.

import abc

from config import Config
from definitions import Table
from sql_dbms import SQL_DBMS
from logger import logger

class OracleSQL(SQL_DBMS, abc.ABC):
    is_rowdependencies: bool = None
    reserved_keywords: frozenset = frozenset(
        {'ACCESS', 'ADD', 'ALL', 'ALTER', 'AND', 'ANY', 'AS', 'ASC', 'AUDIT', 'BETWEEN', 'BY', 'CHAR',
         'CHECK', 'CLUSTER', 'COLUMN', 'COLUMN_VALUE', 'COMMENT', 'COMPRESS', 'CONNECT', 'CREATE', 'CURRENT',
         'DATE', 'DECIMAL', 'DEFAULT',
         'DELETE', 'DESC', 'DISTINCT', 'DROP', 'ELSE', 'EXCLUSIVE', 'EXISTS', 'FILE', 'FLOAT', 'FOR', 'FROM',
         'GRANT', 'GROUP', 'HAVING',
         'IDENTIFIED', 'IMMEDIATE', 'IN', 'INCREMENT', 'INDEX', 'INITIAL', 'INSERT', 'INTEGER', 'INTERSECT', 'INTO',
         'IS', 'LEVEL', 'LIKE',
         'LOCK', 'LONG', 'MAXEXTENTS', 'MINUS', 'MLSLABEL', 'MODE', 'MODIFY', 'NESTED_TABLE_ID', 'NOAUDIT',
         'NOCOMPRESS', 'NOT', 'NOWAIT',
         'NULL', 'NUMBER', 'OF', 'OFFLINE', 'ON', 'ONLINE', 'OPTION', 'OR', 'ORDER', 'PCTFREE', 'PRIOR', 'PUBLIC',
         'RAW', 'RENAME', 'RESOURCE',
         'REVOKE', 'ROW', 'ROWID', 'ROWNUM', 'ROWS', 'SELECT', 'SESSION', 'SET', 'SHARE', 'SIZE', 'SMALLINT',
         'START', 'SUCCESSFUL', 'SYNONYM',
         'SYSDATE', 'TABLE', 'THEN', 'TO', 'TRIGGER', 'UID', 'UNION', 'UNIQUE', 'UPDATE', 'USER', 'VALIDATE',
         'VALUES', 'VARCHAR', 'VARCHAR2',
         'VIEW', 'WHENEVER', 'WHERE', 'WITH'})

    @staticmethod
    def build_insert_query(table_name: str, columns_names: str, values: list):
        return f"insert into {table_name} ({', '.join(columns_names)})\n\t\t values ({', '.join(values)});\n"

    @staticmethod
    def build_delete_query(table_name: str, columns_names: str, values: list):
        delete_query: str = f"delete from {table_name} where "
        delete_conditions: list = []
        for column_name, value in zip(columns_names, values):
            delete_conditions.append(f"{column_name} = {value}")

        delete_query += ' and '.join(delete_conditions) + ';\n'
        return delete_query

    @staticmethod
    def create_ddl_queries(table: Table):
        index_queries: list = []
        nested_table_queries: list = []
        comment_queries: list = []
        sequences_queries: list = []
        # lists to return
        drop_seq_queries: list = []
        fk_queries: list = []
        fk_drop_queries: list = []
        create_table_queries: list = []
        drop_table_queries: list = []

        create_query = f"create table {table.name} (\n"
        for column in table.columns:
            if column.data_type.upper() == 'NAN':
                logger.error(f"Error: the column {table.name}.{column.name} does not have a type")
            create_query = f"{create_query}\t{column.name.ljust(40)} {column.data_type.ljust(20)} "

            if column.default_value != 'nan':
                create_query = f"{create_query}default {column.default_value} "

            if column.identity != 'nan':
                # set the cache for the identity column / sequence
                cache = ''
                if column.cache.isdigit():
                    if int(column.cache) <= 0:
                        logger.warning(f"Cannot define cache smaller then 1 in {table.name}.{column.name}")
                    else:
                        cache = 'cache ' + column.cache
                elif column.cache == 'nocache':
                    cache = 'nocache'

                if column.identity == 'always':
                    create_query = f"{create_query}generated always as identity {cache} "
                elif column.identity == 'default':
                    create_query = f"{create_query}generated by default as identity {cache}  "
                elif column.identity == 'default on null':
                    create_query = f"{create_query}generated by default on null as identity {cache}  "
                elif column.identity == 'seq':
                    sequence_name = f"SEQ_{table.name}_{column.name}"
                    sequence_query = f"create sequence {sequence_name} {cache};\n" \
                                     f"alter table {table.name} modify {column.name} default {sequence_name}.nextval;\n"
                    sequences_queries.append(sequence_query)
                    drop_seq_query = f"drop sequence {sequence_name};\n"
                    drop_seq_queries.append(drop_seq_query)
                else:
                    logger.error(f'Wrong input for identity column in table {table.name}, column {column.name}')

            if column.is_nullable == 'no':
                create_query = f"{create_query}not null "

            if column.constraint != 'nan':
                if column.constraint.lower().startswith('nested'):
                    if column.is_nullable == 'no':
                        logger.error("Nested column can't be 'NOT NULL'")
                    nested_query = f"nested table {column.name} store as {table.name}__{column.name}"
                    nested_table_queries.append(nested_query)
                else:
                    create_query = f"{create_query}{column.constraint} "

            create_query = f"{create_query},\n"

            if column.is_indexed == 'yes':
                if any(x in column.constraint.lower() for x in ["unique", 'primary key']):
                    # Make error in case unique or primary key column are marked to be indexed
                    logger.warning(
                        f"Column {table.name}.{column.name} is already Unique/Primary-key and cannot be indexed")
                index_query = f"create index IDX_{table.name}__{column.name} on {table.name} ({column.name});\n"
                index_queries.append(index_query)

            if column.comment != 'nan':
                comment_query = f"comment on column {table.name}.{column.name} is '{column.comment}';\n"
                if comment_query.count('\'') % 2 != 0:
                    logger.error(f"table: {table.name}, column: {column.name} contains non-escaped single quote")
                comment_queries.append(comment_query)

            if column.foreign_key != 'NAN':
                fk_constraint_name = f"FK_{table.name}__{column.name}"
                # foreign_key in xlsx consist of 2 or 3 parts, separated by comma:
                # first is table name, second is column name, and third is on delete [cascade]\[set null] if exist
                fk_referenced = column.foreign_key.split(',')
                if len(fk_referenced) < 2:
                    logger.error(f"wrong number of arguments in: {table.name}.{column.name} ")
                    exit()
                fk_query = f"alter table {table.name} add constraint {fk_constraint_name} \n" \
                           f"\tforeign key ({column.name}) references {fk_referenced[0].strip()}({fk_referenced[1].strip()})"

                if len(fk_referenced) > 2:
                    fk_query = f"{fk_query} on delete {fk_referenced[2].lower().strip()}"
                fk_query = f"{fk_query};\n"
                fk_queries.append(fk_query)

                fk_drop_query = f"alter table {table.name}\n\t\tdrop constraint {fk_constraint_name};\n"
                fk_drop_queries.append(fk_drop_query)

        create_query = f"{create_query[:-2]}\n) " + "rowdependencies" if Config.is_rowdependencies else f"{create_query[:-2]}\n) "

        for nes_query in nested_table_queries:
            create_query = f"{create_query}\n{nes_query}"

        create_query = f"{create_query};\n"

        # save all queries to global list
        create_table_queries.append(create_query)
        for index_query in index_queries:
            create_table_queries.append(index_query)
        if table.comment != 'nan':
            create_table_queries.append(f"comment on table {table.name} is '{table.comment}';\n")
        for multi_unique_constraint in table.multi_columns_unique:
            constraint_name = '_'.join(multi_unique_constraint.split(','))
            constraint_name = f"UNIQUE_{table.name}__{constraint_name}"
            multi_unique_query = f"alter table {table.name}\n\t" \
                                 f"add constraint {constraint_name}\n\t" \
                                 f"unique ({multi_unique_constraint});\n"
            create_table_queries.append(multi_unique_query)
            fk_drop_queries.append(f"alter table {table.name}\n\tdrop constraint {constraint_name};\n")

        for comment_query in comment_queries:
            create_table_queries.append(comment_query)
        for seq_query in sequences_queries:
            create_table_queries.append(seq_query)

        create_table_queries.append('\n\n')

        drop_table_query = f"drop table {table.name};\n"
        drop_table_queries.append(drop_table_query)

        return drop_seq_queries, fk_queries, fk_drop_queries, create_table_queries, drop_table_queries